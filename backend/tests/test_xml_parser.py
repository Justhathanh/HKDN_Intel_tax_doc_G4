"""Test cho G4T-61 / G4T-46: phần an toàn và mã lỗi của parser XML.

KHÔNG có dữ liệu hóa đơn mẫu trong file này. Test trích xuất trường (số hóa đơn, MST, ngày, số tiền, XML path)
sẽ viết trên dataset chính thức của G4T-42 (Khiêm phụ trách, PO xác nhận chuẩn XML) sau khi dataset đó được
đưa lên và review. Các chuỗi dưới đây chỉ là cấu trúc kỹ thuật hoặc chuỗi tấn công, không phải dữ liệu nghiệp vụ.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import jobs
from app.db import SessionLocal
from app.main import store
from app.models import Document
from app.xml_parser import XML_ERRORS, XmlParseError, direction, parse_invoice_xml

CLIENT = "KH"  # mã khách hàng trừu tượng, chỉ để gọi hàm
SKELETON = b"<HDon><DLHDon><TTChung/><NDHDon><NBan/></NDHDon></DLHDon></HDon>"  # chỉ khung thẻ, không có giá trị


@pytest.mark.parametrize("data,code", [
    (b"<a><b>", "xml_malformed"),
    (b"khong phai xml", "xml_malformed"),
    (b"", "xml_malformed"),
    (b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>', "xml_unsafe"),
    (b'<!DOCTYPE a SYSTEM "http://example.invalid/a.dtd"><a/>', "xml_unsafe"),
    (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY e SYSTEM "file:///etc/passwd">]><r>&e;</r>', "xml_unsafe"),
    (b"<kiem-tra/>", "xml_unsupported_variant"),
    (b"<HDon><Khac/></HDon>", "xml_unsupported_variant"),
    (b"<HDon><DLHDon><TTChung/></DLHDon></HDon>", "xml_schema_invalid"),
    (b"<HDon><DLHDon><TTChung/><NDHDon><NBan/></NDHDon></DLHDon>"
     b"<DLHDon><TTChung/><NDHDon><NBan/></NDHDon></DLHDon></HDon>", "xml_schema_invalid"),
])
def test_errors_have_code_and_message(data, code):
    with pytest.raises(XmlParseError) as info:
        parse_invoice_xml(data, CLIENT)
    assert info.value.code == code and info.value.message == XML_ERRORS[code]


def test_error_does_not_leak_document_content():
    with pytest.raises(XmlParseError) as info:
        parse_invoice_xml(b"<a><b>noi-dung-bi-mat", CLIENT)
    assert "noi-dung-bi-mat" not in str(info.value) and "noi-dung-bi-mat" not in info.value.message


def test_every_xml_error_is_a_safe_job_error():
    for code, message in XML_ERRORS.items():
        assert jobs.SAFE_ERRORS[code] == (False, message)


def test_empty_skeleton_reports_required_fields_missing_not_zero():
    r = parse_invoice_xml(SKELETON, CLIENT, document_id="d", job_id="j")
    assert (r.document_id, r.job_id, r.mapping_version) == ("d", "j", "tct-hdon-v1")
    assert not r.schema_check.passed
    assert r.schema_check.missing_required == ["gross_total", "invoice_number", "issue_date", "seller_name",
                                               "seller_tax_id"]
    for f in r.fields:
        if f.field_name == "direction":
            continue
        assert f.raw_value is None and f.normalized_value is None
        assert f.field_status in ("missing", "not_present") and f.xml_path.startswith("/HDon/")


@pytest.mark.parametrize("seller,buyer,label,status", [
    ("KHAC", CLIENT, "incoming", "present"), (CLIENT, "KHAC", "outgoing", "present"),
    (CLIENT, CLIENT, "unknown", "conflict"), ("KHAC", "KHAC", "unknown", "conflict"),
    ("KHAC", None, "unknown", "conflict")])
def test_direction_rule(seller, buyer, label, status):
    assert direction(CLIENT, seller, buyer) == (label, status)


def test_worker_flow_unsupported_xml_goes_to_dead_letter_with_code(api):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH", "tax_id": "KH-1"}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    r = api.post(f"/batches/{bid}/documents", files={"file": ("a.xml", b'<?xml version="1.0"?><kiem-tra/>')},
                 headers={**head, "Idempotency-Key": str(uuid.uuid4())})
    doc_id = r.json()["document_id"]
    with SessionLocal() as db:
        jobs.enqueue(db, db.get(Document, doc_id))
        job = jobs.claim_next(db, "w1", now=datetime.now(timezone.utc) + timedelta(days=1))
        with pytest.raises(XmlParseError) as info:
            parse_invoice_xml(jobs.read_original(store, db, job), CLIENT, job.document_id, job.id)
        assert jobs.fail(db, job, info.value.code) is None
        db.commit()
        assert (job.status, job.error_code, job.error_retryable) == ("dead_letter", "xml_unsupported_variant", False)
