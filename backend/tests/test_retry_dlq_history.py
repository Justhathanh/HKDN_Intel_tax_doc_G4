"""Kiểm thử cho cụm G4T-73, G4T-74, G4T-75, G4T-76: Retry Policy, Retry Mechanism, DLQ & Job History."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import jobs
from app.db import SessionLocal
from app.jobs import JobStatus
from app.models import Document

XML = b'<?xml version="1.0" encoding="UTF-8"?><HSoThueDTu><maTKhai>01/GTGT</maTKhai></HSoThueDTu>'


def _seed_doc(api, tax_id: str = "0101234567"):
    head = {"X-User": "thuan"}
    cid = api.post("/clients", json={"name": f"Cong ty {tax_id}", "tax_id": tax_id}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "ENG-2026"}, headers=head).json()["id"]
    res = api.post(
        f"/batches/{bid}/documents",
        files={"file": ("to_khai.xml", XML)},
        headers={**head, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 201
    return cid, res.json()["document_id"], head


def test_retry_policy_endpoint_exposes_transient_and_permanent_rules(api):
    res = api.get("/retry-policy", headers={"X-User": "thuan"})
    assert res.status_code == 200
    body = res.json()
    assert body["default_max_attempts"] == 3
    assert body["backoff_base_seconds"] == 30
    assert body["backoff_max_seconds"] == 900
    assert "ocr_timeout" in body["retryable_errors"]
    assert "original_tampered" in body["non_retryable_errors"]


def test_execution_history_records_attempts_duration_and_safe_errors(api):
    _, doc_id, head = _seed_doc(api)
    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)

    with SessionLocal() as db:
        j1 = jobs.active_job(db, doc_id, "extract")
        j1.next_attempt_at = t0
        jobs.claim_next(db, "worker-1", now=t0)
        j2 = jobs.fail(db, j1, "ocr_timeout", now=t0 + timedelta(milliseconds=1250))
        assert j2 is not None
        jobs.claim_next(db, "worker-2", now=t0 + timedelta(seconds=31))
        jobs.succeed(db, j2, "xml-mapper-v1", now=t0 + timedelta(seconds=31, milliseconds=420))
        db.commit()

    hist_res = api.get(f"/documents/{doc_id}/jobs", headers=head)
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["document_id"] == doc_id
    assert hist["total_attempts"] == 2
    assert hist["current_status"] == JobStatus.SUCCEEDED

    first, second = hist["items"]
    assert first["attempt_no"] == 1
    assert first["status"] == JobStatus.FAILED
    assert first["duration_ms"] == 1250
    assert first["error_code"] == "ocr_timeout"
    assert first["error_retryable"] is True
    assert first["error_message"] == jobs.SAFE_ERRORS["ocr_timeout"][1]

    assert second["attempt_no"] == 2
    assert second["retry_of_job_id"] == first["job_id"]
    assert second["correlation_id"] == first["correlation_id"]
    assert second["status"] == JobStatus.SUCCEEDED
    assert second["duration_ms"] == 420
    assert second["error_code"] is None

    single_res = api.get(f"/jobs/{second['job_id']}", headers=head)
    assert single_res.status_code == 200
    assert single_res.json()["job_id"] == second["job_id"]


def test_dead_letter_queue_and_idempotent_manual_retry(api):
    cid_a, doc_a, head_a = _seed_doc(api, tax_id="0100000001")
    _, doc_b, head_b = _seed_doc(api, tax_id="0100000002")

    with SessionLocal() as db:
        ja = jobs.active_job(db, doc_a, "extract")
        jobs.claim_next(db, "worker-1")
        assert jobs.fail(db, ja, "parser_error") is None

        jb = jobs.active_job(db, doc_b, "extract")
        jobs.claim_next(db, "worker-1")
        assert jobs.fail(db, jb, "original_missing") is None
        db.commit()
        ja_id, jb_id = ja.id, jb.id

    # Tenant A chỉ thấy DLQ của riêng mình, không thấy của Tenant B
    dlq_a = api.get("/jobs/dead-letter", headers=head_a)
    assert dlq_a.status_code == 200
    assert dlq_a.json()["total"] == 1
    assert dlq_a.json()["items"][0]["job_id"] == ja_id
    assert dlq_a.json()["items"][0]["error_code"] == "parser_error"

    # Tenant A không thể xem hoặc retry job của Tenant B (404)
    assert api.get(f"/jobs/{jb_id}", headers=head_a).status_code == 404
    assert api.post(f"/jobs/{jb_id}/retry", headers=head_a).status_code == 404

    # Kích hoạt retry thủ công từ dead_letter -> tạo attempt_no mới, giữ correlation_id
    retry_res = api.post(f"/jobs/{ja_id}/retry", headers=head_a)
    assert retry_res.status_code == 201
    retried = retry_res.json()
    assert retried["status"] == JobStatus.QUEUED
    assert retried["attempt_no"] == 2
    assert retried["max_attempts"] == 3
    assert retried["retry_of_job_id"] == ja_id

    # Bấm retry lần nữa khi đang có job queued -> trả về job đang hoạt động (200), không sinh trùng
    dup_retry = api.post(f"/jobs/{ja_id}/retry", headers=head_a)
    assert dup_retry.status_code == 200
    assert dup_retry.json()["job_id"] == retried["job_id"]

    # Sau khi đã có lần thử mới, job dead_letter cũ không còn nằm trong danh sách unresolved_only
    dlq_after = api.get("/jobs/dead-letter", headers=head_a)
    assert dlq_after.json()["total"] == 0
    dlq_all = api.get("/jobs/dead-letter?unresolved_only=false", headers=head_a)
    assert dlq_all.json()["total"] == 1


def test_retry_rejects_non_dead_letter_job(api):
    _, doc_id, head = _seed_doc(api)
    with SessionLocal() as db:
        job = jobs.active_job(db, doc_id, "extract")
        jobs.claim_next(db, "worker-1")
        jobs.succeed(db, job, "xml-mapper-v1")
        db.commit()
        job_id = job.id

    res = api.post(f"/jobs/{job_id}/retry", headers=head)
    assert res.status_code == 409
    assert res.json()["error_code"] == "job_not_retryable"
