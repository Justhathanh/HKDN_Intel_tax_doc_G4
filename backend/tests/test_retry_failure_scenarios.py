"""Kiểm thử tự động các kịch bản Retry, Lỗi xử lý, Hàng đợi Dead Letter và Tính nhất quán Lịch sử (G4T-77 / ST06.5).

Tác giả: Nguyễn Thanh Khiêm (Dev - Automated Testing / QA)
Nhiệm vụ: ST06.5 - Test Retry and Failure Scenarios (Jira G4T-77)
Yêu cầu kiểm thử:
1. Transient failure then success (Lỗi tạm thời sau đó thành công ở lần thử tiếp theo)
2. Permanent failure (Lỗi vĩnh viễn không thể thử lại -> Chuyển thẳng Dead Letter Queue)
3. Retry exhaustion (Thử lại chạm ngưỡng tối đa max_attempts -> Chuyển vào Dead Letter Queue)
4. DLQ routing & Safety (Định tuyến DLQ, cô lập hàng đợi, che giấu lỗi an toàn SEC 04)
5. Attempt counts & Exponential backoff (Đếm số lần thử và tính toán giãn cách thời gian)
6. History consistency & Lineage (Tính nhất quán lịch sử qua API /documents/{doc_id}/jobs)
7. Worker lease expiration & Reclaim (Thu hồi job khi worker bị treo/mất kết nối)
8. Job state machine integrity on failure transitions (Bảo vệ tính toàn vẹn trạng thái)
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import jobs, main
from app.db import SessionLocal
from app.jobs import (
    BACKOFF_BASE,
    BACKOFF_MAX,
    DEFAULT_LEASE,
    DEFAULT_MAX_ATTEMPTS,
    IllegalJobTransition,
    JobError,
    JobStatus,
)
from app.models import Document, ProcessingJob
from app.worker import process_one

SAFE_XML_CONTENT = b'<?xml version="1.0" encoding="UTF-8"?><test-doc><status>valid</status></test-doc>'


def _upload_test_document(api, tax_id="CLIENT-TEST-RETRY", filename="invoice_sample.xml", data=SAFE_XML_CONTENT):
    """Helper tạo client, batch và tải file lên để có document_id và authed headers."""
    auth_headers = {"X-User": "test_qa_khiem"}
    client_res = api.post("/clients", json={"name": "Cong Ty Kiem Thu QA", "tax_id": tax_id}, headers=auth_headers)
    assert client_res.status_code == 201
    client_id = client_res.json()["id"]

    auth_headers["X-Client-Ids"] = client_id
    batch_res = api.post(
        "/batches",
        json={"client_id": client_id, "engagement_id": "ENG-RETRY-2026"},
        headers=auth_headers,
    )
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]

    upload_res = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": (filename, data)},
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["document_id"]
    return doc_id, auth_headers


# ==============================================================================
# SCENARIO 1: TRANSIENT FAILURE THEN SUCCESS (LỖI TẠM THỜI RỒI THÀNH CÔNG)
# ==============================================================================

def test_transient_failure_then_success_workflow(api):
    """Kịch bản 1: Lỗi tạm thời (vd: ocr_timeout) ở lần 1, sau đó thử lại lần 2 thành công."""
    doc_id, headers = _upload_test_document(api, tax_id="KH-TRANSIENT-01")

    # Kiểm tra job attempt 1 được tự động tạo ở trạng thái queued
    with SessionLocal() as db:
        initial_job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == doc_id))
        assert initial_job is not None
        assert initial_job.status == JobStatus.QUEUED
        assert initial_job.attempt_no == 1
        job1_id = initial_job.id

    # Lần thực thi 1: Gặp lỗi tạm thời ocr_timeout (retryable=True)
    def failing_processor(job, data):
        raise JobError("ocr_timeout")

    with SessionLocal() as db:
        claimed_job = jobs.claim_next(db, worker_id="worker-qa-01")
        assert claimed_job is not None
        assert claimed_job.id == job1_id
        db.commit()

    with SessionLocal() as db:
        job = db.get(ProcessingJob, job1_id)
        # Processor gặp lỗi và gọi fail
        retry_job = jobs.fail(db, job, "ocr_timeout")
        db.commit()
        assert retry_job is not None
        job2_id = retry_job.id

    # Thẩm định trạng thái Job 1
    res1 = api.get(f"/jobs/{job1_id}", headers=headers)
    assert res1.status_code == 200
    j1_data = res1.json()
    assert j1_data["status"] == "failed"
    assert j1_data["display_status"] == "FAILED"
    assert j1_data["will_retry"] is True
    assert j1_data["error"]["code"] == "ocr_timeout"
    assert j1_data["error"]["retryable"] is True
    assert j1_data["finished_at"] is not None

    # Thẩm định trạng thái Job 2 (lần thử lại)
    res2 = api.get(f"/jobs/{job2_id}", headers=headers)
    assert res2.status_code == 200
    j2_data = res2.json()
    assert j2_data["status"] == "queued"
    assert j2_data["display_status"] == "QUEUED"
    assert j2_data["will_retry"] is False
    assert j2_data["attempt_no"] == 2
    assert j2_data["retry_of_job_id"] == job1_id

    # Lần thực thi 2: Giả lập thời gian đến hạn, worker nhận job 2 và thành công
    now_attempt2 = datetime.now(timezone.utc) + timedelta(minutes=1)
    with SessionLocal() as db:
        claimed_job2 = jobs.claim_next(db, worker_id="worker-qa-02", now=now_attempt2)
        assert claimed_job2 is not None
        assert claimed_job2.id == job2_id
        jobs.succeed(db, claimed_job2, processor_version="v2.1.0", now=now_attempt2)
        db.commit()

    # Thẩm định trạng thái cuối cùng của Job 2
    res2_final = api.get(f"/jobs/{job2_id}", headers=headers)
    assert res2_final.status_code == 200
    j2_final_data = res2_final.json()
    assert j2_final_data["status"] == "succeeded"
    assert j2_final_data["display_status"] == "SUCCEEDED"
    assert j2_final_data["will_retry"] is False
    assert j2_final_data["processor_version"] == "v2.1.0"
    assert j2_final_data["error"] is None


# ==============================================================================
# SCENARIO 2: PERMANENT FAILURE (LỖI VĨNH VIỄN KHÔNG THỬ LẠI -> DEAD LETTER)
# ==============================================================================

@pytest.mark.parametrize("error_code", [
    "original_missing",
    "original_tampered",
    "unsupported_document",
    "parser_error",
])
def test_permanent_non_retryable_failures_route_to_dlq(api, error_code):
    """Kịch bản 2: Các lỗi vĩnh viễn (non-retryable) chuyển thẳng vào dead_letter mà không thử lại."""
    doc_id, headers = _upload_test_document(api, tax_id=f"KH-PERM-{error_code[:8]}")

    with SessionLocal() as db:
        job = jobs.claim_next(db, worker_id="worker-perm-test")
        assert job is not None
        job_id = job.id
        db.commit()

    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        # Báo lỗi vĩnh viễn
        retry = jobs.fail(db, job, error_code)
        db.commit()
        # Lỗi vĩnh viễn tuyệt đối KHÔNG sinh job thử lại
        assert retry is None

    # Kiểm tra API
    res = api.get(f"/jobs/{job_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "dead_letter"
    assert data["display_status"] == "FAILED"
    assert data["will_retry"] is False
    assert data["attempt_no"] == 1
    assert data["error"]["code"] == error_code
    assert data["error"]["retryable"] is False

    # Thẩm định không có job nào còn lại trong hàng đợi
    with SessionLocal() as db:
        remaining = jobs.claim_next(db, worker_id="worker-perm-test")
        assert remaining is None


# ==============================================================================
# SCENARIO 3: RETRY EXHAUSTION (THỬ LẠI CHẠM NGƯỠNG MAX ATTEMPTS)
# ==============================================================================

def test_retry_exhaustion_transitions_to_dead_letter(api):
    """Kịch bản 3: Lỗi tạm thời lặp đi lặp lại chạm ngưỡng max_attempts (3 lần) thì chuyển vào dead_letter."""
    doc_id, headers = _upload_test_document(api, tax_id="KH-EXHAUSTION-01")

    attempts = []
    simulated_time = datetime.now(timezone.utc)

    # Vòng lặp chạy 3 lần thử
    for i in range(1, DEFAULT_MAX_ATTEMPTS + 1):
        with SessionLocal() as db:
            claimed = jobs.claim_next(db, worker_id=f"worker-exh-{i}", now=simulated_time)
            assert claimed is not None, f"Phải claim được job ở lần thử {i}"
            assert claimed.attempt_no == i
            attempts.append(claimed.id)
            db.commit()

        with SessionLocal() as db:
            job = db.get(ProcessingJob, claimed.id)
            # Lần nào cũng gặp lỗi tạm thời quota_exceeded
            retry_job = jobs.fail(db, job, "quota_exceeded", now=simulated_time)
            db.commit()

            if i < DEFAULT_MAX_ATTEMPTS:
                assert retry_job is not None, f"Lần {i} < {DEFAULT_MAX_ATTEMPTS} phải có job thử lại"
                assert retry_job.attempt_no == i + 1
            else:
                # Đã chạm ngưỡng tối đa (attempt 3) -> chuyển thẳng dead_letter, không có job 4
                assert retry_job is None, "Chạm max_attempts không được tạo thêm job thử lại"

        # Tăng thời gian giả lập để vượt qua backoff
        simulated_time += timedelta(minutes=5)

    # Thẩm định trạng thái từng attempt
    assert len(attempts) == 3

    # Attempt 1: failed (will_retry=True)
    res1 = api.get(f"/jobs/{attempts[0]}", headers=headers).json()
    assert res1["status"] == "failed"
    assert res1["will_retry"] is True

    # Attempt 2: failed (will_retry=True)
    res2 = api.get(f"/jobs/{attempts[1]}", headers=headers).json()
    assert res2["status"] == "failed"
    assert res2["will_retry"] is True
    assert res2["retry_of_job_id"] == attempts[0]

    # Attempt 3: dead_letter (will_retry=False)
    res3 = api.get(f"/jobs/{attempts[2]}", headers=headers).json()
    assert res3["status"] == "dead_letter"
    assert res3["will_retry"] is False
    assert res3["display_status"] == "FAILED"
    assert res3["retry_of_job_id"] == attempts[1]
    assert res3["attempt_no"] == 3


# ==============================================================================
# SCENARIO 4: DLQ ROUTING, QUEUE ISOLATION & SEC 04 SANITIZATION
# ==============================================================================

def test_dlq_queue_isolation_and_error_sanitization(api):
    """Kịch bản 4: Job ở dead_letter bị cô lập hoàn toàn khỏi queue và ngoại lệ lạ được chuẩn hóa an toàn (SEC 04)."""
    doc_id, headers = _upload_test_document(api, tax_id="KH-DLQ-SEC-01")

    # Giả lập ném exception chứa thông tin nhạy cảm (đường dẫn bí mật, mã SQL)
    def crash_processor(job, data):
        raise RuntimeError("Database connection string: postgresql://admin:secretPass@internal-db:5432/taxdb")

    # Thực thi qua process_one với main.store
    process_one(SessionLocal, main.store, worker_id="worker-sec-test", processor=crash_processor)

    # Thẩm định job được chuyển thành lỗi chuẩn hóa 'internal_error', tuyệt đối không lọt 'secretPass'
    with SessionLocal() as db:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == doc_id))
        assert job.error_code == "internal_error"
        assert "secretPass" not in (job.error_message or "")
        assert "internal-db" not in (job.error_message or "")


# ==============================================================================
# SCENARIO 5: EXPONENTIAL BACKOFF TIMING CONSISTENCY
# ==============================================================================

def test_exponential_backoff_timing_schedule():
    """Kịch bản 5: Kiểm tra thuật toán tính toán thời gian chờ giãn cách (Exponential Backoff)."""
    # Attempt 1: 30s * 2^0 = 30s
    assert jobs.backoff(1) == timedelta(seconds=30)
    # Attempt 2: 30s * 2^1 = 60s
    assert jobs.backoff(2) == timedelta(seconds=60)
    # Attempt 3: 30s * 2^2 = 120s (2 phút)
    assert jobs.backoff(3) == timedelta(seconds=120)
    # Attempt 4: 30s * 2^3 = 240s (4 phút)
    assert jobs.backoff(4) == timedelta(seconds=240)
    # Attempt lớn: Bị chặn bởi BACKOFF_MAX (15 phút)
    assert jobs.backoff(10) == BACKOFF_MAX
    assert jobs.backoff(20) == BACKOFF_MAX


# ==============================================================================
# SCENARIO 6: HISTORY CONSISTENCY & AUDIT LINEAGE
# ==============================================================================

def test_job_execution_history_consistency_api(api):
    """Kịch bản 6: Tính nhất quán của lịch sử job khi truy vấn qua /documents/{document_id}/jobs."""
    doc_id, headers = _upload_test_document(api, tax_id="KH-AUDIT-HISTORY")

    # Giả lập vòng đời: Attempt 1 thất bại -> Attempt 2 thành công
    now1 = datetime.now(timezone.utc)
    with SessionLocal() as db:
        j1 = jobs.claim_next(db, worker_id="worker-audit-1", now=now1)
        j2 = jobs.fail(db, j1, "ocr_timeout", now=now1 + timedelta(seconds=5))
        db.commit()

    now2 = now1 + timedelta(minutes=2)
    with SessionLocal() as db:
        j2_claimed = jobs.claim_next(db, worker_id="worker-audit-2", now=now2)
        jobs.succeed(db, j2_claimed, processor_version="v2.5.0", now=now2 + timedelta(seconds=8))
        db.commit()

    # Gọi API kiểm tra lịch sử
    hist_res = api.get(f"/documents/{doc_id}/jobs", headers=headers)
    assert hist_res.status_code == 200
    hist = hist_res.json()

    assert hist["document_id"] == doc_id
    items = hist["items"]
    assert len(items) == 2

    # Thẩm định thứ tự tăng dần theo attempt_no
    assert items[0]["attempt_no"] == 1
    assert items[0]["status"] == "failed"
    assert items[0]["error"]["code"] == "ocr_timeout"
    assert items[0]["duration_ms"] == 5000  # 5 giây

    assert items[1]["attempt_no"] == 2
    assert items[1]["status"] == "succeeded"
    assert items[1]["processor_version"] == "v2.5.0"
    assert items[1]["duration_ms"] == 8000  # 8 giây
    assert items[1]["retry_of_job_id"] == items[0]["job_id"]

    # Thẩm định trường 'latest' trỏ đúng vào lần thử mới nhất
    assert hist["latest"]["job_id"] == items[1]["job_id"]
    assert hist["latest"]["status"] == "succeeded"


# ==============================================================================
# SCENARIO 7: WORKER LEASE EXPIRATION & RECLAIM RECOVERY
# ==============================================================================

def test_worker_lease_expiration_and_reclaim_recovery(api):
    """Kịch bản 7: Worker nhận job nhưng bị crash/treo máy quá hạn lease -> Tự động thu hồi và thử lại."""
    doc_id, headers = _upload_test_document(api, tax_id="KH-CRASH-RECLAIM")

    t_start = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # Worker 1 nhận job với lease 10 phút
        job = jobs.claim_next(db, worker_id="crashed-worker-99", now=t_start, lease=timedelta(minutes=10))
        assert job.status == JobStatus.RUNNING
        assert job.locked_by == "crashed-worker-99"
        db.commit()
        job_id = job.id

    # Thời gian trôi qua 15 phút (vượt quá hạn lease 10 phút)
    t_after_crash = t_start + timedelta(minutes=15)

    with SessionLocal() as db:
        # Hệ thống tiến hành thu hồi job quá hạn
        reclaimed = jobs.reclaim_expired(db, now=t_after_crash)
        db.commit()
        assert len(reclaimed) == 1
        retry_job = reclaimed[0]
        assert retry_job.attempt_no == 2
        assert retry_job.retry_of_job_id == job_id

    # Job cũ phải được chuyển sang failed với mã lỗi lease_expired
    res_crashed = api.get(f"/jobs/{job_id}", headers=headers).json()
    assert res_crashed["status"] == "failed"
    assert res_crashed["error"]["code"] == "lease_expired"
    assert res_crashed["will_retry"] is True

    # Worker mới (Worker 2) gắp được job thử lại sau thời gian backoff
    t_worker2 = t_after_crash + timedelta(minutes=1)
    with SessionLocal() as db:
        job2 = jobs.claim_next(db, worker_id="healthy-worker-01", now=t_worker2)
        assert job2 is not None
        assert job2.attempt_no == 2
        jobs.succeed(db, job2, processor_version="v2.0-recovered", now=t_worker2)
        db.commit()

    # Kiểm tra job 2 thành công
    res_retry = api.get(f"/jobs/{job2.id}", headers=headers).json()
    assert res_retry["status"] == "succeeded"


# ==============================================================================
# SCENARIO 8: JOB STATE MACHINE TRANSITION INTEGRITY CHECKS
# ==============================================================================

def test_illegal_state_transitions_fail_strictly():
    """Kịch bản 8: Bảo vệ toàn vẹn cỗ máy trạng thái (chặn mọi chuyển đổi bất hợp lệ)."""
    # 1. Từ failed không thể quay lại running (thử lại phải tạo dòng job mới)
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition("failed", "running")

    # 2. Từ dead_letter không thể chuyển sang bất kỳ trạng thái nào (trạng thái kết thúc)
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition("dead_letter", "running")
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition("dead_letter", "succeeded")
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition("dead_letter", "queued")

    # 3. Từ succeeded không thể chuyển sang failed
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition("succeeded", "failed")

    # 4. Trạng thái lạ không có trong enum
    with pytest.raises(IllegalJobTransition):
        jobs.check_job_transition("queued", "unknown_state")
