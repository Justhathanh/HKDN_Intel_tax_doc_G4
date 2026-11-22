"""Kiểm thử tích hợp luồng xử lý tài liệu nền (G4T-72 / ST05.7).

Tác giả: Nguyễn Thanh Khiêm (Dev – Automated Testing)
Căn cứ:
- G4T-66: Thiết kế Processing Job Schema
- G4T-67: Xây dựng Job State Machine
- G4T-68: Hoàn thiện Processing API Contract (docs/G4T-68-hop-dong-api-xu-ly.md)
- G4T-69/70/71: Background Queue & Worker Processing
- G4T-72 (ST05.7 Jira): Test job creation after upload, queue handoff, worker execution,
  state transitions, failure handling and the separation between upload response and asynchronous processing.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import jobs
from app.db import SessionLocal
from app.jobs import JobStatus
from app.main import store
from app.models import Batch, Client, Document, ProcessingJob
from app.worker import process_one

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hoa don gia tri gia tang</THDon>
            <KHMSHDon>1</KHMSHDon>
            <KHHDon>1C26TNN</KHHDon>
            <SHDon>0000045</SHDon>
            <NLap>2026-03-15</NLap>
            <DVTTe>VND</DVTTe>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>CONG TY CP CONG NGHE THONG TIN BAO AN</Ten>
                <MST>0109988776</MST>
            </NBan>
            <NMua>
                <Ten>CONG TY TNHH PHAT TRIEN PHAN MEM THANG LONG</Ten>
                <MST>0108877665</MST>
            </NMua>
            <TToan>
                <TgTTTBSo>49500000</TgTTTBSo>
            </TToan>
        </NDHDon>
    </DLHDon>
</HDon>
"""

T0 = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)


def _create_client_and_batch(api, tax_id="0108877665", user_name="khiem_tester"):
    """Tạo client và batch hợp lệ, trả về (client_id, batch_id, headers)."""
    headers = {"X-User": user_name}
    c_res = api.post(
        "/clients",
        json={"name": "Cong ty THTax Test Khiem", "tax_id": tax_id},
        headers=headers,
    )
    assert c_res.status_code == 201
    client_id = c_res.json()["id"]

    headers["X-Client-Ids"] = client_id
    b_res = api.post(
        "/batches",
        json={"client_id": client_id, "engagement_id": "ENG-2026-INT"},
        headers=headers,
    )
    assert b_res.status_code == 201
    batch_id = b_res.json()["id"]

    return client_id, batch_id, headers


def test_upload_separation_and_auto_job_creation(api):
    """1. Tách biệt phản hồi upload (201) và tự động đưa job vào hàng đợi (queued)."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0108877665")
    file_bytes = SAMPLE_XML
    expected_digest = hashlib.sha256(file_bytes).hexdigest()

    # Upload tài liệu: phản hồi ngay HTTP 201 không bị nghẽn
    res = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("hoa_don_vat10.xml", file_bytes, "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 201
    doc_info = res.json()
    doc_id = doc_info["document_id"]
    assert doc_info["status"] == "received"
    assert doc_info["duplicate"] is False
    assert doc_info["sha256"] == expected_digest

    # Kiểm tra Processing Job được tự động sinh ngầm trong Database
    with SessionLocal() as db:
        jobs_in_db = db.scalars(
            select(ProcessingJob).where(ProcessingJob.document_id == doc_id)
        ).all()
        assert len(jobs_in_db) == 1
        job = jobs_in_db[0]
        assert job.status == JobStatus.QUEUED
        assert job.attempt_no == 1
        assert job.max_attempts == 3
        assert job.input_sha256 == expected_digest
        assert job.correlation_id is not None
        job_id = job.id

    # Frontend đọc chi tiết trạng thái qua GET /jobs/{job_id} theo API Contract (G4T-68)
    job_res = api.get(f"/jobs/{job_id}", headers=headers)
    assert job_res.status_code == 200
    job_body = job_res.json()
    assert job_body["job_id"] == job_id
    assert job_body["document_id"] == doc_id
    assert job_body["status"] == "queued"
    assert job_body["display_status"] == "QUEUED"
    assert job_body["will_retry"] is False
    assert job_body["error"] is None
    assert job_body["attempt_no"] == 1


def test_e2e_queue_handoff_and_worker_execution_success(api):
    """2. Luồng tích hợp end-to-end: Upload -> Handoff Worker -> Succeeded -> Kiểm tra qua API."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0109988776")

    upload_res = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("invoice_standard.xml", SAMPLE_XML, "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["document_id"]

    # Worker lấy job từ hàng đợi và thực thi
    processed_job_id = process_one(SessionLocal, store, worker_id="worker-integration-01")
    assert processed_job_id is not None

    # Gọi API GET /jobs/{job_id} xác nhận trạng thái SUCCEEDED
    job_res = api.get(f"/jobs/{processed_job_id}", headers=headers)
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["status"] == "succeeded"
    assert job_data["display_status"] == "SUCCEEDED"
    assert job_data["processor_version"] is not None
    assert job_data["started_at"] is not None
    assert job_data["finished_at"] is not None
    assert job_data["error"] is None

    # Gọi API GET /documents/{document_id}/jobs kiểm tra lịch sử xử lý
    history_res = api.get(f"/documents/{doc_id}/jobs", headers=headers)
    assert history_res.status_code == 200
    history_body = history_res.json()
    assert history_body["document_id"] == doc_id
    assert len(history_body["items"]) == 1
    assert history_body["latest"]["job_id"] == processed_job_id
    assert history_body["latest"]["display_status"] == "SUCCEEDED"


def test_batch_upload_multiple_documents_asynchronous_queue(api):
    """3. Nộp nhiều tài liệu cùng một lô: mỗi file nhận 201 ngay và hàng đợi xử lý tuần tự."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0318991122")

    doc_ids = []
    # Nộp 3 file khác nhau vào cùng 1 lô
    for i in range(1, 4):
        xml_content = SAMPLE_XML.replace(b"0000045", f"00000{i}0".encode())
        res = api.post(
            f"/batches/{batch_id}/documents",
            files={"file": (f"invoice_{i}.xml", xml_content, "application/xml")},
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert res.status_code == 201
        doc_ids.append(res.json()["document_id"])

    # Xác nhận trong DB có đủ 3 queued jobs tương ứng với 3 documents
    with SessionLocal() as db:
        queued_jobs = db.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.document_id.in_(doc_ids))
            .where(ProcessingJob.status == JobStatus.QUEUED)
        ).all()
        assert len(queued_jobs) == 3

    # Worker lần lượt xử lý sạch hàng đợi
    processed_count = 0
    while True:
        job_id = process_one(SessionLocal, store, worker_id="batch-worker")
        if job_id is None:
            break
        processed_count += 1

    assert processed_count == 3

    # Xác nhận từng document qua API đều có trạng thái hoàn tất SUCCEEDED
    for d_id in doc_ids:
        r = api.get(f"/documents/{d_id}/jobs", headers=headers)
        assert r.status_code == 200
        assert r.json()["latest"]["display_status"] == "SUCCEEDED"


def test_worker_state_transitions_during_execution(api):
    """4. Kiểm tra máy trạng thái (State Machine): queued -> running (có lease lock) -> succeeded."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0401882233")

    up_res = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("state_doc.xml", SAMPLE_XML, "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    doc_id = up_res.json()["document_id"]

    # Bước 1: Trạng thái ban đầu: QUEUED
    with SessionLocal() as db:
        job = db.scalars(select(ProcessingJob).where(ProcessingJob.document_id == doc_id)).one()
        job_id = job.id
        assert job.status == JobStatus.QUEUED

    # Bước 2: Worker 1 claim job -> chuyển sang RUNNING với lease
    with SessionLocal() as db:
        claimed_job = jobs.claim_next(db, worker_id="worker-lock-1", now=T0)
        assert claimed_job is not None
        assert claimed_job.id == job_id
        assert claimed_job.status == JobStatus.RUNNING
        assert claimed_job.locked_by == "worker-lock-1"
        assert claimed_job.lease_expires_at > T0
        db.commit()

    # Kiểm tra API GET /jobs/{job_id} khi đang chạy: display_status = RUNNING
    running_res = api.get(f"/jobs/{job_id}", headers=headers)
    assert running_res.status_code == 200
    assert running_res.json()["display_status"] == "RUNNING"

    # Bước 3: Worker 2 cố gắng claim khi lease đang hiệu lực -> không được lấy trùng (bảo vệ lease)
    with SessionLocal() as db:
        another_claim = jobs.claim_next(db, worker_id="worker-lock-2", now=T0 + timedelta(seconds=5))
        assert another_claim is None  # Queue rỗng vì job đang bị khóa bởi worker 1

    # Bước 4: Worker 1 hoàn thành xử lý -> chuyển sang SUCCEEDED
    with SessionLocal() as db:
        job_to_finish = db.get(ProcessingJob, job_id)
        jobs.succeed(db, job_to_finish, processor_version="xml-parser-v2.0", now=T0 + timedelta(seconds=10))
        db.commit()

    done_res = api.get(f"/jobs/{job_id}", headers=headers)
    assert done_res.status_code == 200
    assert done_res.json()["display_status"] == "SUCCEEDED"


def test_failure_handling_retry_and_dead_letter_integration(api):
    """5. Kiểm tra xử lý lỗi: retry có backoff, vượt quá 3 lần vào Dead Letter Queue."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0201993344")

    up_res = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("fail_doc.xml", SAMPLE_XML, "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    doc_id = up_res.json()["document_id"]

    # Giả lập 3 lần gặp lỗi tạm thời (ocr_timeout)
    now = T0
    with SessionLocal() as db:
        # Attempt 1: Lỗi tạm thời -> sinh attempt 2 với will_retry=True
        now += timedelta(minutes=1)
        j1 = jobs.claim_next(db, "w-fail", now=now)
        assert j1.attempt_no == 1
        jobs.fail(db, j1, "ocr_timeout", now=now)

        # Attempt 2: Lỗi tạm thời tiếp tục
        now += timedelta(minutes=10)
        j2 = jobs.claim_next(db, "w-fail", now=now)
        assert j2.attempt_no == 2
        assert j2.retry_of_job_id == j1.id
        jobs.fail(db, j2, "ocr_timeout", now=now)

        # Attempt 3: Đã đủ max_attempts (3) -> Chuyển vào dead_letter
        now += timedelta(minutes=20)
        j3 = jobs.claim_next(db, "w-fail", now=now)
        assert j3.attempt_no == 3
        jobs.fail(db, j3, "ocr_timeout", now=now)
        assert j3.status == JobStatus.DEAD_LETTER
        db.commit()

    # Gọi API kiểm tra lịch sử qua hợp đồng G4T-68
    hist_res = api.get(f"/documents/{doc_id}/jobs", headers=headers)
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    items = hist_data["items"]
    assert len(items) == 3

    # Kiểm tra attempt 1 và 2 là FAILED (will_retry=True)
    assert items[0]["attempt_no"] == 1 and items[0]["will_retry"] is True
    assert items[1]["attempt_no"] == 2 and items[1]["will_retry"] is True

    # Kiểm tra attempt 3 (latest) vào DEAD_LETTER (will_retry=False)
    assert items[2]["attempt_no"] == 3 and items[2]["status"] == "dead_letter"
    assert items[2]["will_retry"] is False
    assert hist_data["latest"]["status"] == "dead_letter"
    assert hist_data["latest"]["display_status"] == "FAILED"
    assert hist_data["latest"]["error"]["code"] == "ocr_timeout"


def test_tenant_isolation_integration(api):
    """6. Bảo mật cách ly khách hàng (Tenant Isolation): Khách A không được truy cập Job khách B."""
    # Tạo Client A và nộp tài liệu
    _, batch_a, headers_a = _create_client_and_batch(api, tax_id="0109999991", user_name="user_a")
    res_a = api.post(
        f"/batches/{batch_a}/documents",
        files={"file": ("client_a_doc.xml", SAMPLE_XML, "application/xml")},
        headers={**headers_a, "Idempotency-Key": str(uuid.uuid4())},
    )
    doc_id_a = res_a.json()["document_id"]

    with SessionLocal() as db:
        job_a = db.scalars(select(ProcessingJob).where(ProcessingJob.document_id == doc_id_a)).one()
        job_id_a = job_a.id

    # Tạo Client B hoàn toàn độc lập
    _, _, headers_b = _create_client_and_batch(api, tax_id="0109999992", user_name="user_b")

    # Client B cố tình đọc Job của Client A -> Bị từ chối 404 Not Found (Bảo mật tuyệt đối phạm vi)
    r_job = api.get(f"/jobs/{job_id_a}", headers=headers_b)
    assert r_job.status_code == 404
    assert r_job.json()["error_code"] == "not_found"

    # Client B cố tình xem lịch sử Job của Document A -> Bị từ chối 404 Not Found
    r_doc_jobs = api.get(f"/documents/{doc_id_a}/jobs", headers=headers_b)
    assert r_doc_jobs.status_code == 404
    assert r_doc_jobs.json()["error_code"] == "not_found"


def test_non_eligible_upload_does_not_enqueue_job(api):
    """7. Tài liệu bị lỗi upload (file rỗng 0 byte) bị từ chối và KHÔNG đưa vào hàng đợi."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0107778899")

    # Nộp file rỗng 0 byte
    res = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("empty.xml", b"", "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == "empty_file"

    # Xác nhận hàng đợi không có bất kỳ job nào
    with SessionLocal() as db:
        jobs_count = db.scalars(select(ProcessingJob)).all()
        assert len(jobs_count) == 0


def test_duplicate_upload_links_to_existing_job_without_re_enqueue(api):
    """8. Nộp trùng file (cùng SHA-256) dùng lại Document cũ, không sinh job trùng lặp lãng phí."""
    _, batch_id, headers = _create_client_and_batch(api, tax_id="0106665544")

    # Nộp lần 1: tạo document mới và sinh 1 job
    res1 = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("doc_origin.xml", SAMPLE_XML, "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res1.status_code == 201
    doc_id_1 = res1.json()["document_id"]

    # Nộp lần 2 (cùng nội dung, Idempotency-Key mới): hệ thống nhận diện file trùng lặp
    res2 = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("doc_copy.xml", SAMPLE_XML, "application/xml")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res2.status_code == 200
    assert res2.json()["duplicate"] is True
    assert res2.json()["document_id"] == doc_id_1

    # Kiểm tra DB chỉ có duy nhất 1 job, không sinh job thứ 2
    with SessionLocal() as db:
        jobs_list = db.scalars(select(ProcessingJob)).all()
        assert len(jobs_list) == 1
