"""G4T-16: kiểm tra định dạng PDF, JPG, PNG, XML. Toàn bộ là dữ liệu giả."""
import io
import uuid

import pytest
from PIL import Image
from pypdf import PdfWriter

from app import safety

XML = '<?xml version="1.0" encoding="UTF-8"?><HDon><SHDon>0000123</SHDon></HDon>'.encode()


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def image(fmt):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, fmt)
    return buf.getvalue()


def setup(api):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH A", "tax_id": "0312345678"}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    return bid, head


def send(api, bid, head, name, data):
    return api.post(f"/batches/{bid}/documents", files={"file": (name, data)},
                    headers={**head, "Idempotency-Key": str(uuid.uuid4())})


@pytest.mark.parametrize("name,make,kind", [
    ("a.pdf", pdf, "pdf"),
    ("A.PDF", pdf, "pdf"),
    ("a.jpg", lambda: image("JPEG"), "jpg"),
    ("a.jpeg", lambda: image("JPEG"), "jpg"),
    ("A.JPG", lambda: image("JPEG"), "jpg"),
    ("a.png", lambda: image("PNG"), "png"),
    ("A.PNG", lambda: image("PNG"), "png"),
    ("a.xml", lambda: XML, "xml"),
    ("A.XML", lambda: XML, "xml"),
    ("hóa đơn tháng 10.xml", lambda: XML, "xml"),
])
def test_supported_format_accepted(name, make, kind):
    verdict = safety.inspect(name, make())
    assert verdict.ok and verdict.kind == kind


@pytest.mark.parametrize("data", [
    b"\xef\xbb\xbf" + XML,
    b"  \r\n" + b"<HDon></HDon>",
    '<?xml version="1.0" encoding="UTF-16"?><HDon>Hóa đơn</HDon>'.encode("utf-16"),
    "\ufeff<HDon>Hóa đơn</HDon>".encode("utf-16-be"),
], ids=["utf8-bom", "khoang-trang-dau", "utf16-le", "utf16-be"])
def test_xml_encodings_accepted(data):
    verdict = safety.inspect("a.xml", data)
    assert verdict.ok and verdict.kind == "xml"


@pytest.mark.parametrize("name,data", [
    ("a.txt", b"van ban"),
    ("a.docx", b"PK\x03\x04aaa"),
    ("a.csv", b"a,b\n1,2\n"),
    ("a.gif", b"GIF89a....."),
    ("a.tiff", b"II*\x00...."),
    ("a.html", b"<html></html>"),
    ("a.svg", b"<svg></svg>"),
    ("a.pdf.exe", b"MZ\x90"),
    ("khong_co_duoi", XML),
    ("a.", XML),
    (".xml", b"MZ\x90"),
])
def test_unsupported_format_rejected(name, data):
    verdict = safety.inspect(name, data)
    assert not verdict.ok and verdict.reason in ("unsupported_format", "archive_not_supported")


def test_api_accepts_supported_format(api):
    bid, head = setup(api)
    r = send(api, bid, head, "a.xml", XML)
    assert r.status_code == 201 and r.json()["mime_type"] == "application/xml"


@pytest.mark.parametrize("name,data", [("a.txt", b"van ban"), ("a.gif", b"GIF89a.....")])
def test_api_rejects_with_clear_error(api, name, data):
    bid, head = setup(api)
    r = send(api, bid, head, name, data)
    assert r.status_code == 415
    body = r.json()
    assert body["error_code"] == "unsupported_format" and "PDF, JPG, PNG, XML" in body["message"]
    item = api.get(f"/batches/{bid}/manifest", headers=head).json()["items"][0]
    assert item["outcome"] == "rejected" and item["document_id"] is None
