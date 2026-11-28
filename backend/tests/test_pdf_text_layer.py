"""Đọc lớp chữ PDF theo trang và gắn vào worker (G4T-62, ST08).

Không có dữ liệu tự tạo:
- PDF hóa đơn, PDF scan, PDF 3 trang: dataset chính thức G4T-42 (tests/fixtures, Khiêm, PR #15).
- PDF hỏng, PDF có mật khẩu: bộ file kiểm thử chính thức của G4T-17 (docs/test/files).
- Ca "PDF vừa có trang chữ vừa có trang scan" ghép trong bộ nhớ từ đúng hai trang chính thức ở trên,
  không ghi file mới vào repo và không thêm nội dung nào.
"""
import hashlib
import io
import json
import uuid
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from app import jobs, main
from app.db import SessionLocal
from app.domain_models import DocumentValidation, ExtractedField, ExtractionRun
from app.extraction import extract_processor
from app.jobs import JobError, JobStatus
from app.models import Document, ProcessingJob
from app.pdf_text import EXTRACTOR_NAME, PdfTextError, extract_pdf_text
from app.worker import process_one
from scripts.evaluate_pdf_text_layer import evaluate

FIXTURES = Path(__file__).parent / "fixtures"
TEST_FILES = Path(__file__).resolve().parents[2] / "docs" / "test" / "files"
GROUND_TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))["files"]

DIGITAL = "invoice_digital_text_layer.pdf"
SCANNED = "invoice_scanned_no_text.pdf"
MULTI = "mixed_documents_multi_page.pdf"


def _official(name: str) -> bytes:
    return (FIXTURES / GROUND_TRUTH[name]["relative_path"]).read_bytes()


def _text_then_scan() -> bytes:
    """Trang 1 = trang hóa đơn có chữ, trang 2 = trang scan; cả hai lấy nguyên từ file chính thức."""
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(_official(DIGITAL))).pages[0])
    writer.add_page(PdfReader(io.BytesIO(_official(SCANNED))).pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ---------- Đánh giá trên dataset chính thức ----------

def test_report_on_official_dataset_is_all_correct():
    report = evaluate()
    assert report["routing"] == {"correct": 5, "total": 5}
    assert report["page_count"] == {"correct": 1, "total": 1}
    assert report["text_values"]["found"] == report["text_values"]["total"] == 16


# ---------- Bộ đọc: theo trang, không trả chữ rỗng như thành công ----------

def test_digital_invoice_text_is_read_per_page_without_ocr():
    result = extract_pdf_text(_official(DIGITAL))
    assert (result.outcome, result.page_count, result.ocr_pages) == ("parsed", 1, [])
    page = result.pages[0]
    assert page.page_number == 1 and page.has_text_layer
    fields = GROUND_TRUTH[DIGITAL]["fields"]
    for key in ("invoice_series", "invoice_number", "seller_tax_id", "buyer_tax_id"):
        assert fields[key] in page.text, key  # giữ nguyên số 0 đầu, ví dụ số hóa đơn 00000088
    assert "HÓA ĐƠN GIÁ TRỊ GIA TĂNG" in page.text  # giữ dấu tiếng Việt


def test_scanned_pdf_is_marked_for_ocr_not_empty_success():
    result = extract_pdf_text(_official(SCANNED))
    assert (result.outcome, result.ocr_pages, result.text_pages) == ("needs_ocr", [1], [])
    assert result.pages[0].reason == "no_text_layer"


def test_multi_page_pdf_keeps_page_numbers():
    result = extract_pdf_text(_official(MULTI))
    assert result.page_count == GROUND_TRUTH[MULTI]["total_pages"] == 3
    assert [p.page_number for p in result.pages] == [1, 2, 3]
    assert result.outcome == "parsed"
    # mỗi trang chứa đúng loại chứng từ của nó, không bị dồn chữ sang trang khác
    assert "HÓA ĐƠN" in result.pages[0].text.upper()
    assert "THÔNG BÁO" in result.pages[1].text.upper()
    assert "NỘP TIỀN" in result.pages[2].text.upper()


def test_only_pages_without_text_go_to_ocr():
    result = extract_pdf_text(_text_then_scan())
    assert (result.outcome, result.text_pages, result.ocr_pages) == ("needs_ocr", [1], [2])


@pytest.mark.parametrize("name, code", [
    ("corrupt_invoice.pdf", "pdf_unreadable"),
    ("fake_pdf.pdf", "pdf_unreadable"),
    ("empty_file.pdf", "pdf_unreadable"),
    ("password_protected.pdf", "pdf_encrypted"),
])
def test_unreadable_pdfs_return_fixed_codes(name, code):
    with pytest.raises(PdfTextError) as err:
        extract_pdf_text((TEST_FILES / name).read_bytes())
    assert err.value.code == code
    assert not jobs.SAFE_ERRORS[code][0]  # file không đổi, thử lại vô ích


# ---------- Qua worker: lưu theo trang, gắn document_id + job_id ----------

def _upload(api, name: str, data: bytes) -> tuple[str, dict]:
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH", "tax_id": GROUND_TRUTH[DIGITAL]["fields"]["buyer_tax_id"]},
                   headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    r = api.post(f"/batches/{bid}/documents", files={"file": (name, data)},
                 headers={**head, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.json()
    return r.json()["document_id"], head


def _results(db, job):
    run = db.scalar(select(ExtractionRun).where(ExtractionRun.job_id == job.id))
    fields = list(db.scalars(select(ExtractedField).where(ExtractedField.extraction_run_id == run.id)
                             .order_by(ExtractedField.field_name)))
    rule = db.scalar(select(DocumentValidation).where(DocumentValidation.document_id == job.document_id,
                                                       DocumentValidation.rule_code == "pdf_text_layer_available"))
    return run, fields, rule


def test_worker_saves_digital_pdf_text_by_page(api):
    data = _official(DIGITAL)
    doc_id, head = _upload(api, "hoa_don.pdf", data)
    job_id = process_one(SessionLocal, main.store, worker_id="w-pdf")
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        assert (job.document_id, job.status) == (doc_id, JobStatus.SUCCEEDED)
        assert job.processor_version.startswith(EXTRACTOR_NAME)
        run, fields, rule = _results(db, job)
        assert (run.document_id, run.status, run.metadata_json["outcome"]) == (doc_id, "succeeded", "parsed")
        assert len(fields) == 1
        page = fields[0]
        assert (page.field_name, page.field_status, page.extraction_method) == ("page_text", "present", "pdf_text")
        assert page.source_anchor["page_number"] == 1 and page.source_anchor["needs_ocr"] is False
        assert GROUND_TRUTH[DIGITAL]["fields"]["invoice_number"] in page.normalized_value
        assert (rule.status, rule.details["job_id"], rule.details["extraction_run_id"]) == ("passed", job.id, run.id)
        # bản gốc không đổi: đọc lại vẫn khớp mã băm lúc nhận
        assert hashlib.sha256(jobs.read_original(main.store, db, job)).hexdigest() == \
            hashlib.sha256(data).hexdigest() == db.get(Document, doc_id).sha256
    assert api.get(f"/jobs/{job_id}", headers=head).json()["display_status"] == "SUCCEEDED"


def test_worker_marks_scanned_pdf_for_ocr(api):
    doc_id, _ = _upload(api, "hoa_don_scan.pdf", _official(SCANNED))
    job_id = process_one(SessionLocal, main.store, worker_id="w-pdf")
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        run, fields, rule = _results(db, job)
        assert (run.status, run.metadata_json["ocr_pages"]) == ("needs_ocr", [1])
        page = fields[0]
        # không lưu chuỗi rỗng như thể đã đọc được
        assert (page.field_status, page.raw_value, page.normalized_value) == ("missing", None, None)
        assert page.source_anchor == {"page_number": 1, "char_count": 0, "needs_ocr": True,
                                      "reason": "no_text_layer"}
        assert (rule.status, rule.details["ocr_pages"]) == ("failed", [1])


def test_worker_saves_each_page_of_multi_page_pdf(api):
    _upload(api, "ho_so_3_trang.pdf", _official(MULTI))
    job_id = process_one(SessionLocal, main.store, worker_id="w-pdf")
    with SessionLocal() as db:
        _, fields, _ = _results(db, db.get(ProcessingJob, job_id))
        assert sorted(f.source_anchor["page_number"] for f in fields) == [1, 2, 3]
        assert {f.field_status for f in fields} == {"present"}


def test_unreadable_pdf_fails_with_traceable_run(api):
    """Upload đã chặn PDF hỏng; đây là lớp phòng thủ thứ hai khi bộ đọc gặp file không mở được."""
    _upload(api, "hoa_don.pdf", _official(DIGITAL))
    with SessionLocal() as db:
        job = jobs.claim_next(db, worker_id="w-pdf")
        with pytest.raises(JobError) as err:
            extract_processor(job, (TEST_FILES / "corrupt_invoice.pdf").read_bytes())
        assert err.value.code == "pdf_unreadable"
        run = db.scalar(select(ExtractionRun).where(ExtractionRun.job_id == job.id))
        assert (run.status, run.error_code, run.document_id) == ("failed", "pdf_unreadable", job.document_id)
