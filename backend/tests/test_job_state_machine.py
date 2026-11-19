"""Test cho G4T-67: state machine của processing job. Toàn bộ là dữ liệu giả."""
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import jobs
from app.db import SessionLocal
from app.jobs import JOB_ALLOWED, IllegalJobTransition, JobStatus
from app.models import Document, ProcessingJob
from tests.test_processing_jobs import XML, upload

S = JobStatus
T0 = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)

# Bảng chuyển trạng thái được thống nhất trong docs/G4T-67-state-machine-job.md.
# Nếu ai sửa JOB_ALLOWED mà không sửa tài liệu thì test này báo.
EXPECTED = {
    (S.QUEUED, S.RUNNING),
    (S.RUNNING, S.SUCCEEDED),
    (S.RUNNING, S.FAILED),
    (S.RUNNING, S.DEAD_LETTER),
}


@pytest.mark.parametrize("current,target", list(product(S, S)))
def test_full_transition_matrix(current, target):
    if (current, target) in EXPECTED:
        jobs.check_job_transition(current, target)
    else:
        with pytest.raises(IllegalJobTransition):
            jobs.check_job_transition(current, target)


def test_table_matches_document():
    assert {(a, b) for a, targets in JOB_ALLOWED.items() for b in targets} == EXPECTED
    assert set(JOB_ALLOWED) == set(S)


def test_terminal_and_active_sets():
    assert jobs.TERMINAL_JOB_STATUSES == {S.SUCCEEDED, S.FAILED, S.DEAD_LETTER}
    assert jobs.ACTIVE_JOB_STATUSES == {S.QUEUED, S.RUNNING}
    assert not jobs.TERMINAL_JOB_STATUSES & jobs.ACTIVE_JOB_STATUSES
    assert jobs.TERMINAL_JOB_STATUSES | jobs.ACTIVE_JOB_STATUSES == set(S)
    assert all(jobs.is_terminal(s) for s in ("succeeded", "failed", "dead_letter"))
    assert not jobs.is_terminal("queued") and not jobs.is_terminal("running")


@pytest.mark.parametrize("value", ["QUEUED", "done", "", "cancelled"])
def test_unknown_status_is_rejected(value):
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition(value, S.RUNNING)
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition(S.QUEUED, value)


def test_error_message_explains_why():
    with pytest.raises(IllegalJobTransition, match="lần thử lại là một dòng job mới"):
        jobs.check_job_transition(S.FAILED, S.QUEUED)
    with pytest.raises(IllegalJobTransition, match="trạng thái cuối"):
        jobs.check_job_transition(S.SUCCEEDED, S.RUNNING)


def _running_job(db, doc_id, max_attempts=3):
    jobs.enqueue(db, db.get(Document, doc_id), max_attempts=max_attempts)
    return jobs.claim_next(db, "w1", now=T0 + timedelta(days=1))


@pytest.mark.parametrize("finish", ["succeed", "dead_letter", "failed"])
def test_terminal_job_cannot_be_finished_again(api, finish):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = _running_job(db, doc_id)
        if finish == "succeed":
            jobs.succeed(db, job, "v1", now=T0)
        elif finish == "dead_letter":
            jobs.fail(db, job, "parser_error", now=T0)
        else:
            jobs.fail(db, job, "ocr_timeout", now=T0)
        for action in (lambda: jobs.succeed(db, job, "v1"), lambda: jobs.fail(db, job, "ocr_timeout")):
            with pytest.raises(IllegalJobTransition):
                action()


def test_queued_job_cannot_finish_without_running(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        with pytest.raises(IllegalJobTransition):
            jobs.succeed(db, job, "v1")
        with pytest.raises(IllegalJobTransition):
            jobs.fail(db, job, "parser_error")
        assert job.status == S.QUEUED


def test_retry_path_ends_in_dead_letter_and_keeps_history(api):
    """queued → running → failed → (dòng mới) queued → running → failed → ... → dead_letter."""
    doc_id = upload(api)
    with SessionLocal() as db:
        jobs.enqueue(db, db.get(Document, doc_id), correlation_id="req-9")
        now = T0
        for _ in range(3):
            now += timedelta(hours=1)
            job = jobs.claim_next(db, "w1", now=now)
            jobs.fail(db, job, "ocr_unavailable", now=now)
        db.commit()
        rows = db.scalars(select(ProcessingJob).where(ProcessingJob.document_id == doc_id)
                          .order_by(ProcessingJob.attempt_no)).all()
        assert [(r.attempt_no, r.status) for r in rows] == [(1, "failed"), (2, "failed"), (3, "dead_letter")]
        assert rows[1].retry_of_job_id == rows[0].id and rows[2].retry_of_job_id == rows[1].id
        assert {r.correlation_id for r in rows} == {"req-9"}
        assert jobs.active_job(db, doc_id, "extract") is None
        assert jobs.claim_next(db, "w1", now=now + timedelta(days=1)) is None


def test_new_job_allowed_after_terminal(api):
    """Sau trạng thái cuối, chạy lại = tạo job mới (ví dụ người duyệt yêu cầu xử lý lại)."""
    doc_id = upload(api)
    with SessionLocal() as db:
        first = _running_job(db, doc_id)
        jobs.fail(db, first, "parser_error", now=T0)
        again = jobs.enqueue(db, db.get(Document, doc_id))
        assert again.id != first.id and again.status == S.QUEUED and again.attempt_no == 2
        assert first.status == S.DEAD_LETTER


def test_database_rejects_unknown_status(api):
    doc_id = upload(api)
    with SessionLocal() as db:
        job = jobs.enqueue(db, db.get(Document, doc_id))
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE processing_jobs SET status = 'done' WHERE id = :id"), {"id": job.id})
            db.flush()
        db.rollback()


@pytest.mark.parametrize("attempt_no,max_attempts", [(0, 3), (4, 3)])
def test_database_rejects_bad_attempt_numbers(api, attempt_no, max_attempts):
    doc_id = upload(api, data=XML + f"<!--{attempt_no}-->".encode())
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        db.add(ProcessingJob(client_id=doc.client_id, document_id=doc.id, job_type="extract", status="queued",
                             attempt_no=attempt_no, max_attempts=max_attempts, correlation_id="c",
                             input_sha256=doc.sha256))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
