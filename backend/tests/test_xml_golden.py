"""Golden test parser XML trên dataset chính thức G4T-42 và lưu kết quả qua worker (G4T-61, G4T-46).

Không có dữ liệu tự tạo: mọi mẫu lấy từ tests/fixtures (Khiêm, PR #15, PO xác nhận nhãn). Các ca "sai ở mức
tài liệu" được tạo bằng cách sửa MỘT giá trị trong mẫu chính thức ngay trong test.
"""
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app import main
from app.db import SessionLocal
from app.domain_models import DocumentValidation, ExtractedField, ExtractionRun
from app.extraction import document_findings
from app.jobs import JobStatus
from app.models import ProcessingJob
from app.worker import process_one
from app.xml_parser import XmlParseError, parse_invoice_xml
from scripts.evaluate_xml_dataset import evaluate

FIXTURES = Path(__file__).parent / "fixtures"
GROUND_TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))["files"]
XML_CASES = {k: v for k, v in GROUND_TRUTH.items() if v.get("format", "").lower() == "xml" and not v.get("expected_error")}


@pytest.mark.parametrize("name", sorted(XML_CASES))
def test_every_ground_truth_field_matches(name):
    meta = XML_CASES[name]
    result = parse_invoice_xml((FIXTURES / meta["relative_path"]).read_bytes(), meta["client_tax_id"])
    values = {f.field_name: f.normalized_value for f in result.fields}
    assert {k: values.get(k) for k in meta["fields"]} == meta["fields"]
    assert values["direction"] == meta["expected_direction"]
    assert result.schema_check.passed is meta["schema_passed"]


def test_malformed_sample_returns_expected_code():
    meta = GROUND_TRUTH["malformed_invoice.xml"]
    with pytest.raises(XmlParseError) as info:
        parse_invoice_xml((FIXTURES / meta["relative_path"]).read_bytes(), "")
    assert info.value.code == meta["expected_error"]


def test_two_level_report_on_official_dataset():
    """Hai lớp được báo riêng; số liệu này cũng ghi trong docs/G4T-61-parse-xml-hoa-don.md."""
    report = evaluate(FIXTURES)
    assert report["field_level"] == {"correct": 143, "total": 143, "accuracy": 1.0}
    assert report["document_level"] == {"correct": 7, "total": 7}
    assert report["error_cases"] == {"correct": 1, "total": 1}


def _official(name: str) -> bytes:
    return (FIXTURES / GROUND_TRUTH[name]["relative_path"]).read_bytes()


def test_fields_all_valid_but_document_wrong():
    """Ca trưởng nhóm yêu cầu: từng trường riêng lẻ đều hợp lệ nhưng tổng tiền sai ở mức tài liệu."""
    meta = GROUND_TRUTH["tct_hdon_01_vat10_standard.xml"]
    gross = meta["fields"]["gross_total"]
    data = _official("tct_hdon_01_vat10_standard.xml").decode().replace(
        f"<TgTTTBSo>{gross}</TgTTTBSo>", f"<TgTTTBSo>{int(gross) + 1}</TgTTTBSo>").encode()
    result = parse_invoice_xml(data, meta["client_tax_id"])
    by_name = {f.field_name: f for f in result.fields}
    assert by_name["gross_total"].field_status == "present"           # lớp trường: vẫn hợp lệ
    assert result.schema_check.passed
    findings = {f["rule_code"]: f["status"] for f in document_findings(result)}
    assert findings["totals_consistent"] == "failed"                   # lớp tài liệu: sai
    report_doc_ok = not [s for s in findings.values() if s == "failed"]
    assert report_doc_ok is False


def test_field_wrong_does_not_hide_document_findings():
    """Ngược lại: một trường sai định dạng không làm mất các kết luận ở mức tài liệu."""
    meta = GROUND_TRUTH["tct_hdon_01_vat10_standard.xml"]
    data = _official("tct_hdon_01_vat10_standard.xml").decode().replace(
        f"<NLap>{meta['fields']['issue_date']}</NLap>", "<NLap>01/11/2026</NLap>").encode()
    result = parse_invoice_xml(data, meta["client_tax_id"])
    assert {f.field_name: f.field_status for f in result.fields}["issue_date"] == "needs_review"
    findings = {f["rule_code"]: f["status"] for f in document_findings(result)}
    assert findings["totals_consistent"] == "passed" and findings["direction_determined"] == "passed"


def test_tax_breakdown_rule_on_multi_rate_invoice():
    result = parse_invoice_xml(_official("tct_hdon_02_vat8_multi_rate.xml"),
                               GROUND_TRUTH["tct_hdon_02_vat8_multi_rate.xml"]["client_tax_id"])
    findings = {f["rule_code"]: f["status"] for f in document_findings(result)}
    assert findings["tax_breakdown_consistent"] == "passed"


# ---------- Qua worker: kết quả thật, gắn document_id + job_id ----------

def _upload(api, name: str, data: bytes, tax_id: str) -> tuple[str, dict]:
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH", "tax_id": tax_id}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    r = api.post(f"/batches/{bid}/documents", files={"file": (name, data)},
                 headers={**head, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.json()
    return r.json()["document_id"], head


def test_worker_saves_field_and_document_results(api):
    name = "tct_hdon_01_vat10_standard.xml"
    meta = GROUND_TRUTH[name]
    doc_id, head = _upload(api, name, _official(name), meta["client_tax_id"])

    job_id = process_one(SessionLocal, main.store, worker_id="w-golden")
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        assert (job.document_id, job.status) == (doc_id, JobStatus.SUCCEEDED)
        run = db.scalar(select(ExtractionRun).where(ExtractionRun.job_id == job.id))
        assert (run.document_id, run.status, run.extractor_name) == (doc_id, "succeeded", "xml-parser")
        fields = {f.field_name: f for f in db.scalars(
            select(ExtractedField).where(ExtractedField.extraction_run_id == run.id))}
        assert fields["invoice_number"].normalized_value == meta["fields"]["invoice_number"]
        assert fields["invoice_number"].source_anchor == {"xml_path": "/HDon/DLHDon/TTChung/SHDon"}
        assert {f.extraction_method for f in fields.values()} == {"xml"}
        assert fields["direction"].normalized_value == meta["expected_direction"]
        rules = {v.rule_code: v for v in db.scalars(
            select(DocumentValidation).where(DocumentValidation.document_id == doc_id))}
        assert rules["totals_consistent"].status == "passed"
        assert rules["totals_consistent"].details["job_id"] == job.id
    assert api.get(f"/jobs/{job_id}", headers=head).json()["display_status"] == "SUCCEEDED"


def test_worker_does_not_report_success_for_unsupported_image(api):
    """Ảnh chưa có bộ xử lý (chờ OCR G4T-23): job lỗi unsupported_document thay vì SUCCEEDED giả.
    PDF nay đã có bộ đọc lớp chữ (G4T-62, tests/test_pdf_text_layer.py)."""
    image = (FIXTURES / GROUND_TRUTH["invoice_vat10_retail.jpg"]["relative_path"]).read_bytes()
    _upload(api, "hoa_don.jpg", image, "KH-IMG")
    job_id = process_one(SessionLocal, main.store, worker_id="w-golden")
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        assert (job.status, job.error_code) == (JobStatus.DEAD_LETTER, "unsupported_document")
        assert db.scalar(select(ExtractionRun).where(ExtractionRun.job_id == job.id)) is None


# ---------- Trường thiếu, trùng, ngày: sửa MỘT giá trị trong mẫu chính thức ----------

def _parse_mutated(name: str, old: str, new: str):
    meta = GROUND_TRUTH[name]
    data = _official(name).decode()
    assert old in data, old
    return parse_invoice_xml(data.replace(old, new, 1).encode(), meta["client_tax_id"])


def test_duplicate_field_is_conflict_on_both_levels():
    name = "tct_hdon_01_vat10_standard.xml"
    number = GROUND_TRUTH[name]["fields"]["invoice_number"]
    result = _parse_mutated(name, f"<SHDon>{number}</SHDon>", f"<SHDon>{number}</SHDon><SHDon>{number}9</SHDon>")
    field = result.field("invoice_number")
    assert (field.field_status, field.normalized_value) == ("conflict", None)       # lớp trường: không tự chọn
    findings = {f["rule_code"]: f["status"] for f in document_findings(result)}
    assert findings["no_field_conflicts"] == "failed"                               # lớp tài liệu


def test_missing_required_field_is_missing_not_zero_on_both_levels():
    name = "tct_hdon_01_vat10_standard.xml"
    gross = GROUND_TRUTH[name]["fields"]["gross_total"]
    result = _parse_mutated(name, f"<TgTTTBSo>{gross}</TgTTTBSo>", "<TgTTTBSo></TgTTTBSo>")
    field = result.field("gross_total")
    assert (field.field_status, field.raw_value, field.normalized_value) == ("missing", None, None)
    findings = {f["rule_code"]: f["status"] for f in document_findings(result)}
    assert findings["required_fields_present"] == "failed"
    assert findings["totals_consistent"] == "skipped"                                # không suy ra giá trị thiếu


def test_leading_zeros_and_exact_decimal_from_official_samples():
    meta = GROUND_TRUTH["tct_hdon_03_vat0_export_foreign.xml"]
    result = parse_invoice_xml(_official("tct_hdon_03_vat0_export_foreign.xml"), meta["client_tax_id"])
    number = result.field("invoice_number").normalized_value
    assert number == meta["fields"]["invoice_number"] and number.startswith("0")
    assert result.field("exchange_rate").normalized_value == meta["fields"]["exchange_rate"]
    assert result.mapping_version == "tct-hdon-v1"
    assert result.field("invoice_number").xml_path.endswith("/TTChung/SHDon")


def test_replacement_invoice_date_rule():
    """Ca "ngày sai dù từng trường đúng": hóa đơn thay thế mang ngày của hóa đơn gốc SAU ngày lập của chính nó."""
    name = "tct_hdon_05_replacement.xml"
    fields = GROUND_TRUTH[name]["fields"]
    ok = {f["rule_code"]: f["status"] for f in document_findings(
        parse_invoice_xml(_official(name), GROUND_TRUTH[name]["client_tax_id"]))}
    assert ok["related_invoice_date_not_after_issue"] == "passed"

    later = "2099-12-31"
    result = _parse_mutated(name, f"<NLHDCLQuan>{fields['related_invoice_date']}</NLHDCLQuan>",
                            f"<NLHDCLQuan>{later}</NLHDCLQuan>")
    assert result.field("related_invoice_date").field_status == "present"           # lớp trường: hợp lệ
    bad = {f["rule_code"]: f["status"] for f in document_findings(result)}
    assert bad["related_invoice_date_not_after_issue"] == "failed"                  # lớp tài liệu: sai
