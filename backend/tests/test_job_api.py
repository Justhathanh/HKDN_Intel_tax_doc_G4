"""Test cho G4T-68: API đọc trạng thái job theo hợp đồng docs/G4T-68-hop-dong-api-xu-ly.md. Dữ liệu giả."""
import uuid
from datetime import datetime, timedelta, timezone

from app import jobs
from app.db import SessionLocal
from app.models import Document

XML = b'<?xml version="1.0" encoding="UTF-8"?><kiem-tra/>'  # file an toàn trung tính, không phải hóa đơn
T0 = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
JOB_KEYS = {"job_id", "document_id", "job_type", "status", "display_status", "will_retry", "attempt_no",
            "max_attempts", "retry_of_job_id", "correlation_id", "processor_version", "created_at",
            "next_attempt_at", "started_at", "finished_at", "error"}


def setup_doc(api, tax_id="KH-1"):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH", "tax_id": tax_id}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    r = api.post(f"/batches/{bid}/documents", files={"file": ("a.xml", XML)},
                 headers={**head, "Idempotency-Key": str(uuid.uuid4())})
    return r.json()["document_id"], head


def enqueue(doc_id, **kw):
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id), **kw)
        db.commit()
        return job.id


def test_get_queued_job(api):
    doc_id, head = setup_doc(api)
    job_id = enqueue(doc_id, correlation_id="req-1")
    r = api.get(f"/jobs/{job_id}", headers=head)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == JOB_KEYS
    assert (body["status"], body["display_status"], body["will_retry"]) == ("queued", "QUEUED", False)
    assert (body["job_id"], body["document_id"], body["correlation_id"]) == (job_id, doc_id, "req-1")
    assert body["attempt_no"] == 1 and body["error"] is None and body["started_at"] is None
    assert body["created_at"].endswith("Z")


def test_internal_fields_are_not_exposed(api):
    doc_id, head = setup_doc(api)
    body = api.get(f"/jobs/{enqueue(doc_id)}", headers=head).json()
    for hidden in ("locked_by", "lease_expires_at", "input_sha256", "client_id", "error_message"):
        assert hidden not in body


def test_history_with_retry_and_dead_letter(api):
    doc_id, head = setup_doc(api)
    enqueue(doc_id, correlation_id="req-2")
    with SessionLocal() as db:
        now = T0
        for _ in range(3):
            now += timedelta(hours=1)
            jobs.fail(db, jobs.claim_next(db, "w1", now=now), "ocr_unavailable", now=now)
        db.commit()
    r = api.get(f"/documents/{doc_id}/jobs", headers=head)
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert [(j["attempt_no"], j["status"], j["display_status"], j["will_retry"]) for j in items] == [
        (1, "failed", "FAILED", True), (2, "failed", "FAILED", True), (3, "dead_letter", "FAILED", False)]
    assert body["latest"] == items[-1] and body["document_id"] == doc_id
    assert items[1]["retry_of_job_id"] == items[0]["job_id"]
    assert {j["correlation_id"] for j in items} == {"req-2"}
    assert items[2]["error"] == {"code": "ocr_unavailable", "message": jobs.SAFE_ERRORS["ocr_unavailable"][1],
                                 "retryable": True}


def test_succeeded_job(api):
    doc_id, head = setup_doc(api)
    enqueue(doc_id)
    with SessionLocal() as db:
        job = jobs.claim_next(db, "w1", now=T0 + timedelta(days=1))
        jobs.succeed(db, job, "xml-parser 0.1", now=T0 + timedelta(days=1, seconds=3))
        db.commit()
    body = api.get(f"/documents/{doc_id}/jobs", headers=head).json()["latest"]
    assert (body["status"], body["display_status"], body["processor_version"]) == (
        "succeeded", "SUCCEEDED", "xml-parser 0.1")
    assert body["started_at"] and body["finished_at"] and body["error"] is None


def test_document_without_jobs(api):
    doc_id, head = setup_doc(api)
    assert api.get(f"/documents/{doc_id}/jobs", headers=head).json() == {
        "document_id": doc_id, "latest": None, "items": []}


def test_other_job_type_filter(api):
    doc_id, head = setup_doc(api)
    enqueue(doc_id)
    assert api.get(f"/documents/{doc_id}/jobs?job_type=ocr", headers=head).json()["items"] == []


def test_cross_client_and_missing_return_404(api):
    doc_id, head = setup_doc(api)
    job_id = enqueue(doc_id)
    _, other = setup_doc(api, tax_id="KH-2")
    for path in (f"/jobs/{job_id}", f"/documents/{doc_id}/jobs", f"/jobs/{uuid.uuid4()}",
                 f"/documents/{uuid.uuid4()}/jobs"):
        r = api.get(path, headers=other)
        assert r.status_code == 404 and r.json()["error_code"] == "not_found"


def test_requires_login(api):
    doc_id, head = setup_doc(api)
    job_id = enqueue(doc_id)
    for path in (f"/jobs/{job_id}", f"/documents/{doc_id}/jobs"):
        r = api.get(path)
        assert r.status_code == 401 and r.json()["error_code"] == "unauthenticated"


def test_display_status_covers_every_state():
    assert set(jobs.DISPLAY_STATUS) == set(jobs.JobStatus)
    assert set(jobs.DISPLAY_STATUS.values()) == {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED"}
