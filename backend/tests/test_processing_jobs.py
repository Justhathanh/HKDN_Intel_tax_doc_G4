"""Test cho G4T-66: schema và vòng đời processing job. Toàn bộ là dữ liệu giả."""
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import jobs, main
from app.db import SessionLocal
from app.jobs import JobError, JobStatus
from app.models import Document, ProcessingJob

# Chỉ cần một file XML an toàn để tạo tài liệu; nội dung không phải hóa đơn, không phải dữ liệu mẫu nghiệp vụ.
XML = b'<?xml version="1.0" encoding="UTF-8"?><kiem-tra/>'
# Mốc thời gian tương đối: luôn ở tương lai so với lúc chạy, để job vừa tạo (next_attempt_at = giờ thật) đã đến hạn.
T0 = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)


def upload(api, data=XML, name="a.xml", tax_id="KH-1"):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH", "tax_id": tax_id}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    r = api.post(f"/batches/{bid}/documents", files={"file": (name, data)},
                 headers={**head, "Idempotency-Key": str(uuid.uuid4())})
    return r.json()["document_id"]


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def count_jobs(db):
    return db.scalar(select(func.count()).select_from(ProcessingJob))


def test_enqueue_creates_first_attempt(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        job = jobs.enqueue(db, doc, correlation_id="req-1")
        db.commit()
        assert (job.status, job.attempt_no, job.max_attempts) == ("queued", 1, 3)
        assert job.correlation_id == "req-1" and job.input_sha256 == doc.sha256
        assert job.client_id == doc.client_id and job.job_type == "extract"
        assert job.error_code is None and job.started_at is None and str(uuid.UUID(job.id)) == job.id


def test_correlation_id_generated_when_missing(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        assert str(uuid.UUID(job.correlation_id)) == job.correlation_id


def test_enqueue_twice_returns_same_active_job(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        a = jobs.enqueue(db, doc)
        db.commit()
        b = jobs.enqueue(db, doc)
        db.commit()
        assert a.id == b.id and count_jobs(db) == 1


def test_quarantined_document_cannot_be_enqueued(api):
    png_as_pdf = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    doc_id = upload(api, png_as_pdf, "a.pdf")
    with SessionLocal() as db:
        with pytest.raises(jobs.NotProcessable):
            jobs.enqueue(db, db.get(Document, doc_id))


def test_database_allows_only_one_active_job(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        jobs.enqueue(db, doc)
        db.commit()
        db.add(ProcessingJob(client_id=doc.client_id, document_id=doc.id, job_type="extract", status="queued",
                             attempt_no=2, max_attempts=3, correlation_id="x", input_sha256=doc.sha256))
        with pytest.raises(IntegrityError):
            db.commit()


def test_claim_sets_running_and_lease(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        job.next_attempt_at = T0
        db.commit()
        got = jobs.claim_next(db, "worker-1", now=T0)
        db.commit()
        assert got.id == job.id and got.status == "running" and got.locked_by == "worker-1"
        assert aware(got.started_at) == T0 and aware(got.lease_expires_at) == T0 + jobs.DEFAULT_LEASE
        assert jobs.claim_next(db, "worker-2", now=T0) is None


def test_succeed_is_final(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        jobs.claim_next(db, "w")
        jobs.succeed(db, job, "xml-mapping-v1")
        db.commit()
        assert job.status == "succeeded" and job.processor_version == "xml-mapping-v1"
        assert job.finished_at is not None and job.locked_by is None and job.lease_expires_at is None
        with pytest.raises(jobs.IllegalJobTransition):
            jobs.succeed(db, job, "v2")


def test_retryable_failure_creates_next_attempt_with_backoff(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id), correlation_id="req-9")
        job.next_attempt_at = T0
        jobs.claim_next(db, "w", now=T0)
        retry = jobs.fail(db, job, "ocr_timeout", now=T0)
        db.commit()
        assert (job.status, job.error_code, job.error_retryable) == ("failed", "ocr_timeout", True)
        assert (retry.status, retry.attempt_no, retry.retry_of_job_id) == ("queued", 2, job.id)
        assert retry.correlation_id == "req-9" and retry.input_sha256 == job.input_sha256
        assert aware(retry.next_attempt_at) == T0 + timedelta(seconds=30)
        assert jobs.claim_next(db, "w", now=T0 + timedelta(seconds=29)) is None
        assert jobs.claim_next(db, "w", now=T0 + timedelta(seconds=30)).id == retry.id


def test_last_attempt_goes_to_dead_letter(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id), max_attempts=2)
        for attempt in (1, 2):
            claimed = jobs.claim_next(db, "w", now=T0 + timedelta(hours=attempt))
            assert claimed.attempt_no == attempt
            nxt = jobs.fail(db, claimed, "ocr_unavailable", now=T0 + timedelta(hours=attempt))
        db.commit()
        assert nxt is None and claimed.status == "dead_letter"
        statuses = db.scalars(select(ProcessingJob.status).order_by(ProcessingJob.attempt_no)).all()
        assert statuses == ["failed", "dead_letter"]


def test_non_retryable_failure_goes_straight_to_dead_letter(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        jobs.claim_next(db, "w")
        assert jobs.fail(db, job, "parser_error") is None
        db.commit()
        assert job.status == "dead_letter" and count_jobs(db) == 1


def test_error_metadata_is_safe(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        jobs.claim_next(db, "w")
        jobs.fail(db, job, "Traceback ... noi-dung-tai-lieu /srv/originals/abc")
        db.commit()
        assert job.error_code == "internal_error"
        assert job.error_message == jobs.SAFE_ERRORS["internal_error"][1]
        assert "noi-dung-tai-lieu" not in job.error_message and "/srv" not in job.error_message


def test_backoff_is_capped():
    assert jobs.backoff(1) == timedelta(seconds=30) and jobs.backoff(2) == timedelta(seconds=60)
    assert jobs.backoff(20) == jobs.BACKOFF_MAX


def test_job_cannot_skip_running():
    with pytest.raises(jobs.IllegalJobTransition):
        jobs.check_job_transition("queued", JobStatus.SUCCEEDED)
    with pytest.raises(jobs.IllegalJobTransition):
        jobs.check_job_transition("dead_letter", JobStatus.RUNNING)


def test_read_original_checks_hash_and_never_writes(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        doc = db.get(Document, doc_id)
        path = main.store.root / doc.storage_key
        before = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        assert jobs.read_original(main.store, db, job) == XML
        assert (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) == before


def test_read_original_detects_tampering_and_missing(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        path = main.store.root / db.get(Document, doc_id).storage_key
        os.chmod(path, 0o644)
        path.write_bytes(b"<kiem-tra>da bi sua</kiem-tra>")
        with pytest.raises(JobError) as tampered:
            jobs.read_original(main.store, db, job)
        assert tampered.value.code == "original_tampered"
        path.unlink()
        with pytest.raises(JobError) as missing:
            jobs.read_original(main.store, db, job)
        assert missing.value.code == "original_missing"


def test_unknown_job_error_code_becomes_internal_error():
    assert JobError("something_else").code == "internal_error"


def test_expired_lease_is_reclaimed(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        job.next_attempt_at = T0
        jobs.claim_next(db, "crashed-worker", now=T0, lease=timedelta(minutes=5))
        assert jobs.reclaim_expired(db, now=T0 + timedelta(minutes=4)) == []
        retries = jobs.reclaim_expired(db, now=T0 + timedelta(minutes=6))
        db.commit()
        assert job.status == "failed" and job.error_code == "lease_expired"
        assert len(retries) == 1 and retries[0].attempt_no == 2


def test_jobs_follow_document_client(api):
    a = upload(api, tax_id="KH-1")
    b = upload(api, data=XML + b" ", tax_id="KH-2")
    with SessionLocal() as db:
        ja, jb = (jobs.enqueue(db, db.get(Document, d)) for d in (a, b))
        assert ja.client_id != jb.client_id
        assert {ja.client_id, jb.client_id} == {db.get(Document, a).client_id, db.get(Document, b).client_id}


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="cần PostgreSQL")
def test_concurrent_enqueue_and_claim(api):
    doc_ids = [upload(api, data=XML + f"<!--{i}-->".encode()) for i in range(3)]
    assert all(doc_ids)

    def enqueue_once(_):
        with SessionLocal() as db:
            try:
                job = jobs.enqueue(db, db.get(Document, doc_ids[0]))
                db.commit()
                return job.id
            except IntegrityError:
                db.rollback()
                return jobs.active_job(db, doc_ids[0], "extract").id

    with ThreadPoolExecutor(8) as pool:
        ids = set(pool.map(enqueue_once, range(16)))
    assert len(ids) == 1
    with SessionLocal() as db:
        for d in doc_ids[1:]:
            jobs.enqueue(db, db.get(Document, d))
        db.commit()

    def claim(worker):
        with SessionLocal() as db:
            job = jobs.claim_next(db, worker)
            db.commit()
            return job.id if job else None

    with ThreadPoolExecutor(6) as pool:
        claimed = [c for c in pool.map(claim, [f"w{i}" for i in range(6)]) if c]
    assert len(claimed) == 3 and len(set(claimed)) == 3
