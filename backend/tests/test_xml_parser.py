"""Test cho G4T-61 / G4T-46: parse trực tiếp XML hóa đơn. Toàn bộ là dữ liệu giả (tests/fixtures/xml)."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import jobs
from app.db import SessionLocal
from app.main import store
from app.models import Document
from app.xml_parser import (PARSER_VERSION, XML_ERRORS, XmlParseError, XmlParseResult, direction,
                            parse_invoice_xml)

FIXTURES = Path(__file__).parent / "fixtures" / "xml"
BUYER, SELLER = "0312345678", "0109876543"


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def values(result: XmlParseResult) -> dict[str, str | None]:
    return {f.field_name: f.normalized_value for f in result.fields}


def statuses(result: XmlParseResult) -> dict[str, str]:
    return {f.field_name: f.field_status for f in result.fields}


# ---------- Mẫu hợp lệ cho chuẩn đang hỗ trợ ----------

def test_incoming_invoice_all_header_fields():
    r = parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER, document_id="d1", job_id="j1")
    v = values(r)
    assert (r.document_id, r.job_id, r.mapping_version, r.processor_version) == ("d1", "j1", "tct-hdon-v1",
                                                                                 PARSER_VERSION)
    assert r.schema_check.passed and r.schema_check.missing_required == [] and r.schema_check.conflicts == []
    assert v["invoice_form"] == "1" and v["invoice_series"] == "C26TAA"
    assert v["issue_date"] == "2026-11-10" and v["currency"] == "VND"
    assert (v["net_total"], v["tax_total"], v["gross_total"]) == ("12000000", "1160000", "13160000")
    assert v["direction"] == "incoming"
    assert v["tax_authority_code"] == "00ABCDEF0123456789ABCDEF0123456789"


def test_identifiers_stay_strings_with_leading_zeros():
    r = parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER)
    f = r.field("invoice_number")
    assert f.raw_value == "00000045" and f.normalized_value == "00000045"
    assert isinstance(f.normalized_value, str)
    assert r.field("seller_tax_id").normalized_value == "0109876543"


def test_vietnamese_unicode_preserved():
    r = parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER)
    assert r.field("seller_name").raw_value == "Công ty TNHH Thương Mại Mẫu Thử Một"
    assert r.field("buyer_name").normalized_value == "Công ty Cổ phần Dịch Vụ Mẫu Thử Hai"
    assert r.field("gross_total_in_words").raw_value == "Mười ba triệu một trăm sáu mươi nghìn đồng"


def test_decomposed_unicode_is_normalized_but_raw_kept():
    nfd = "Cơ sở Mẫu Thử".encode("utf-8").decode("utf-8")
    import unicodedata
    decomposed = unicodedata.normalize("NFD", nfd)
    xml = load("tct_hdon_incoming.xml").decode().replace("Công ty TNHH Thương Mại Mẫu Thử Một", decomposed)
    f = parse_invoice_xml(xml.encode(), BUYER).field("seller_name")
    assert f.raw_value == decomposed and f.normalized_value == unicodedata.normalize("NFC", decomposed)


def test_xml_path_provenance_for_every_field():
    r = parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER)
    assert r.field("invoice_number").xml_path == "/HDon/DLHDon/TTChung/SHDon"
    assert r.field("seller_tax_id").xml_path == "/HDon/DLHDon/NDHDon/NBan/MST"
    assert r.field("gross_total").xml_path == "/HDon/DLHDon/NDHDon/TToan/TgTTTBSo"
    assert all(f.xml_path for f in r.fields if f.field_name != "direction")
    assert all(f.extraction_method == "xml" for f in r.fields)


def test_tax_breakdown_rows_with_indexed_paths():
    r = parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER)
    v = values(r)
    assert (v["tax_breakdown[1].rate"], v["tax_breakdown[1].net_amount"], v["tax_breakdown[1].tax_amount"]) == (
        "10%", "10000000", "1000000")
    assert (v["tax_breakdown[2].rate"], v["tax_breakdown[2].tax_amount"]) == ("8%", "160000")
    assert r.field("tax_breakdown[2].tax_amount").xml_path == \
        "/HDon/DLHDon/NDHDon/TToan/THTTLTSuat/LTSuat[2]/TThue"


def test_line_items_are_not_extracted():
    names = {f.field_name for f in parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER).fields}
    assert not any("HHDVu" in n or "item" in n for n in names)  # EXT 03: không lấy dòng hàng trong Core


def test_outgoing_with_namespace_branch_tax_id_and_foreign_currency():
    r = parse_invoice_xml(load("tct_hdon_outgoing_ns.xml"), "0312345678-001")
    v, s = values(r), statuses(r)
    assert v["direction"] == "outgoing" and v["seller_tax_id"] == "0312345678-001"
    assert v["invoice_number"] == "0000007" and v["issue_date"] == "2026-11-12"
    assert v["currency"] == "USD" and v["exchange_rate"] == "25350.5" and v["gross_total"] == "1500.00"
    assert s["buyer_tax_id"] == "not_present"  # bên mua nước ngoài không có MST: không tự bịa (EXT 03)
    assert r.field("invoice_number").xml_path == "/HDon/DLHDon/TTChung/SHDon"


def test_replacement_invoice_keeps_lifecycle_reference():
    v = values(parse_invoice_xml(load("tct_hdon_replacement.xml"), BUYER))
    assert v["related_invoice_nature"] == "1"
    assert (v["related_invoice_series"], v["related_invoice_number"], v["related_invoice_date"]) == (
        "C26TAA", "00000045", "2026-11-10")


def test_lifecycle_fields_absent_on_normal_invoice():
    s = statuses(parse_invoice_xml(load("tct_hdon_incoming.xml"), BUYER))
    assert s["related_invoice_number"] == "not_present"


def test_wrapped_invoice_and_personal_identifier():
    r = parse_invoice_xml(load("tct_hdon_wrapped.xml"), BUYER)
    assert r.field("invoice_number").xml_path == "/TDiep/DLieu/HDon/DLHDon/TTChung/SHDon"
    assert r.field("seller_tax_id").normalized_value == "001234567890"
    assert values(r)["direction"] == "incoming"


def test_utf16_encoded_file():
    xml = load("tct_hdon_incoming.xml").decode().replace('encoding="UTF-8"', 'encoding="UTF-16"')
    r = parse_invoice_xml(xml.encode("utf-16"), BUYER)
    assert r.field("seller_name").raw_value == "Công ty TNHH Thương Mại Mẫu Thử Một"


# ---------- Thiếu, mơ hồ, xung đột ----------

def test_missing_is_unknown_not_zero():
    xml = load("tct_hdon_wrapped.xml")
    r = parse_invoice_xml(xml, BUYER)
    for name in ("net_total", "tax_total"):
        f = r.field(name)
        assert (f.raw_value, f.normalized_value, f.field_status) == (None, None, "not_present")


def test_missing_required_field_fails_schema_check_but_keeps_other_fields():
    xml = load("tct_hdon_incoming.xml").decode().replace("<SHDon>00000045</SHDon>", "<SHDon>  </SHDon>")
    r = parse_invoice_xml(xml.encode(), BUYER)
    assert not r.schema_check.passed and r.schema_check.missing_required == ["invoice_number"]
    assert r.field("invoice_number").field_status == "missing"
    assert values(r)["gross_total"] == "13160000"


@pytest.mark.parametrize("raw", ["10/11/2026", "11-10-2026", "2026-13-01", "hôm qua"])
def test_ambiguous_or_bad_date_needs_review(raw):
    xml = load("tct_hdon_incoming.xml").decode().replace("2026-11-10", raw)
    f = parse_invoice_xml(xml.encode(), BUYER).field("issue_date")
    assert (f.raw_value, f.normalized_value, f.field_status) == (raw, None, "needs_review")


@pytest.mark.parametrize("raw", ["13.160.000", "13,160,000", "1.3e7", "abc"])
def test_amount_with_separators_needs_review(raw):
    xml = load("tct_hdon_incoming.xml").decode().replace("<TgTTTBSo>13160000", f"<TgTTTBSo>{raw}")
    f = parse_invoice_xml(xml.encode(), BUYER).field("gross_total")
    assert (f.raw_value, f.normalized_value, f.field_status) == (raw, None, "needs_review")


def test_exact_decimal_not_float():
    xml = load("tct_hdon_outgoing_ns.xml").decode().replace("1500.00</inv:TgTTTBSo>", "0.1000000000000000055</inv:TgTTTBSo>")
    assert values(parse_invoice_xml(xml.encode(), "0312345678-001"))["gross_total"] == "0.1000000000000000055"


@pytest.mark.parametrize("raw", ["031234567", "03123456789", "0312345678-01", "MST0312345678"])
def test_invalid_tax_id_needs_review_and_raw_kept(raw):
    xml = load("tct_hdon_incoming.xml").decode().replace("<MST>0109876543</MST>", f"<MST>{raw}</MST>")
    f = parse_invoice_xml(xml.encode(), BUYER).field("seller_tax_id")
    assert (f.raw_value, f.normalized_value, f.field_status) == (raw, None, "needs_review")


def test_duplicate_field_is_conflict_not_guessed():
    xml = load("tct_hdon_incoming.xml").decode().replace(
        "<SHDon>00000045</SHDon>", "<SHDon>00000045</SHDon><SHDon>00000046</SHDon>")
    r = parse_invoice_xml(xml.encode(), BUYER)
    assert r.field("invoice_number").field_status == "conflict" and r.field("invoice_number").normalized_value is None
    assert "invoice_number" in r.schema_check.conflicts


@pytest.mark.parametrize("seller,buyer,label,status", [
    (SELLER, BUYER, "incoming", "present"), (BUYER, SELLER, "outgoing", "present"),
    (BUYER, BUYER, "unknown", "conflict"), (SELLER, "0100000001", "unknown", "conflict"),
    (SELLER, None, "unknown", "conflict")])
def test_direction(seller, buyer, label, status):
    assert direction(BUYER, seller, buyer) == (label, status)


# ---------- Lỗi có mã ----------

@pytest.mark.parametrize("data,code", [
    (b"<HDon><DLHDon>", "xml_malformed"),
    (b"khong phai xml", "xml_malformed"),
    (b"", "xml_malformed"),
    (b'<!DOCTYPE a [<!ENTITY x "y">]><HDon>&x;</HDon>', "xml_unsafe"),
    (b'<!DOCTYPE a SYSTEM "http://example.invalid/a.dtd"><HDon/>', "xml_unsafe"),
    (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY e SYSTEM "file:///etc/passwd">]><r>&e;</r>', "xml_unsafe"),
    (b"<Invoice><Number>1</Number></Invoice>", "xml_unsupported_variant"),
    (b"<HDon><Khac/></HDon>", "xml_unsupported_variant"),
    (b"<HDon><DLHDon><TTChung/></DLHDon></HDon>", "xml_schema_invalid"),
])
def test_errors_have_code_and_message(data, code):
    with pytest.raises(XmlParseError) as info:
        parse_invoice_xml(data, BUYER)
    assert info.value.code == code and info.value.message == XML_ERRORS[code]


def test_two_invoices_in_one_file_rejected():
    one = load("tct_hdon_replacement.xml").decode()
    body = one.split("<HDon>", 1)[1].rsplit("</HDon>", 1)[0]
    with pytest.raises(XmlParseError) as info:
        parse_invoice_xml(f"<HDon>{body}{body}</HDon>".encode(), BUYER)
    assert info.value.code == "xml_schema_invalid"


def test_error_does_not_leak_document_content():
    with pytest.raises(XmlParseError) as info:
        parse_invoice_xml(b"<HDon><DLHDon><TTChung><SHDon>0000999 bi mat", BUYER)
    assert "0000999" not in str(info.value) and "0000999" not in info.value.message


def test_every_xml_error_is_a_safe_job_error():
    for code, message in XML_ERRORS.items():
        assert jobs.SAFE_ERRORS[code] == (False, message)


# ---------- Nối với job: kết quả mang document_id và job_id ----------

T0 = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)


def _upload(api, data: bytes, name: str):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH", "tax_id": BUYER}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    r = api.post(f"/batches/{bid}/documents", files={"file": (name, data)},
                 headers={**head, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.json()
    return r.json()["document_id"]


def test_worker_flow_links_result_to_document_and_job(api):
    doc_id = _upload(api, load("tct_hdon_incoming.xml"), "hoa-don.xml")
    with SessionLocal() as db:
        jobs.enqueue(db, db.get(Document, doc_id))
        job = jobs.claim_next(db, "w1", now=T0 + timedelta(days=1))
        result = parse_invoice_xml(jobs.read_original(store, db, job), BUYER, document_id=job.document_id,
                                   job_id=job.id)
        jobs.succeed(db, job, f"{result.processor} {result.processor_version}")
        db.commit()
        assert (result.document_id, result.job_id) == (doc_id, job.id)
        assert job.status == "succeeded" and job.processor_version == f"xml-parser {PARSER_VERSION}"
        assert values(result)["invoice_number"] == "00000045"


def test_worker_flow_unsupported_xml_goes_to_dead_letter_with_code(api):
    doc_id = _upload(api, b'<?xml version="1.0"?><Invoice><Number>1</Number></Invoice>', "khac.xml")
    with SessionLocal() as db:
        jobs.enqueue(db, db.get(Document, doc_id))
        job = jobs.claim_next(db, "w1", now=T0 + timedelta(days=1))
        with pytest.raises(XmlParseError) as info:
            parse_invoice_xml(jobs.read_original(store, db, job), BUYER, job.document_id, job.id)
        assert jobs.fail(db, job, info.value.code) is None
        db.commit()
        assert (job.status, job.error_code, job.error_retryable) == ("dead_letter", "xml_unsupported_variant", False)
