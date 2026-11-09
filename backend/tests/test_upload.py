"""Test cho ST01 (G4T-11). Dữ liệu trong file này hoàn toàn là dữ liệu giả."""
import hashlib
import io
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import func, select

from app import main, safety
from app.db import SessionLocal
from app.models import Document, StateEvent
from app.states import IllegalTransition, State, check_transition
from app.storage import LocalWriteOnceStore, OriginalExists

XML = b'<?xml version="1.0" encoding="UTF-8"?><HDon><SHDon>0000123</SHDon></HDon>'


def pdf(pages=1, password=None, js=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(100, 100)
    if js:
        writer.add_js("app.alert(1)")
    if password:
        writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def image(fmt):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, fmt)
    return buf.getvalue()


def setup(api, name="KH A", tax_id="0312345678"):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": name, "tax_id": tax_id}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    return bid, head


def send(api, bid, head, name, data, key=None):
    return api.post(f"/batches/{bid}/documents", files={"file": (name, data)},
                    headers={**head, "Idempotency-Key": key or str(uuid.uuid4())})


def manifest(api, bid, head):
    return api.get(f"/batches/{bid}/manifest", headers=head).json()


# Tiêu chí 1: định dạng hỗ trợ
@pytest.mark.parametrize("name,make,mime,pages", [
    ("a.pdf", lambda: pdf(2), "application/pdf", 2),
    ("a.jpg", lambda: image("JPEG"), "image/jpeg", 1),
    ("a.JPEG", lambda: image("JPEG"), "image/jpeg", 1),
    ("a.png", lambda: image("PNG"), "image/png", 1),
    ("a.xml", lambda: XML, "application/xml", None),
])
def test_supported_formats(api, name, make, mime, pages):
    bid, head = setup(api)
    r = send(api, bid, head, name, make())
    assert r.status_code == 201, r.text
    assert (r.json()["mime_type"], r.json()["page_count"]) == (mime, pages)


# Tiêu chí 2: backend nhận và lưu đúng file
def test_original_stored_intact(api):
    bid, head = setup(api)
    body = send(api, bid, head, "a.xml", XML).json()
    assert body["sha256"] == hashlib.sha256(XML).hexdigest()
    with SessionLocal() as db:
        doc = db.get(Document, body["document_id"])
        assert main.store.get(doc.storage_key) == XML
        events = db.scalars(select(StateEvent).where(StateEvent.document_id == doc.id)).all()
    assert [(e.from_state, e.to_state, e.actor) for e in events] == [(None, "received", "u1")]


# Tiêu chí 3: Document ID duy nhất
def test_document_ids_unique(api):
    bid, head = setup(api)
    ids = {send(api, bid, head, "a.xml", XML + f"<!--{i}-->".encode()).json()["document_id"] for i in range(5)}
    assert len(ids) == 5 and all(str(uuid.UUID(i)) == i for i in ids)


# Tiêu chí 4: phản hồi rõ ràng
def test_receipt_fields(api):
    bid, head = setup(api)
    r = send(api, bid, head, "hóa đơn.xml", XML)
    assert r.status_code == 201
    b = r.json()
    assert b["file_name"] == "hóa đơn.xml" and b["batch_id"] == bid and b["size"] == len(XML)
    assert b["status"] == "received" and b["duplicate"] is False and b["uploaded_by"] == "u1"
    assert b["channel"] == "browser" and b["received_at"].endswith("Z")
    got = api.get(f"/documents/{b['document_id']}", headers=head)
    assert got.status_code == 200 and got.json()["sha256"] == b["sha256"]


# Tiêu chí 5: lỗi rõ ràng và vẫn được ghi lại
@pytest.mark.parametrize("name,make,status,code", [
    ("a.xml", lambda: b"", 400, "empty_file"),
    ("a.exe", lambda: b"MZ\x90", 415, "unsupported_format"),
    ("a.txt", lambda: XML, 415, "unsupported_format"),
    ("a.zip", lambda: b"PK\x03\x04aaa", 415, "archive_not_supported"),
    ("a.pdf", lambda: pdf(31), 422, "too_many_pages"),
    ("a.pdf", lambda: pdf(1, password="x"), 422, "password_protected"),
    ("a.pdf", lambda: b"%PDF-1.4 broken", 422, "corrupt_file"),
    ("a.png", lambda: b"\x89PNG\r\n\x1a\nbroken", 422, "corrupt_file"),
    ("a.xml", lambda: b"<HDon><broken>", 422, "corrupt_file"),
])
def test_rejected_returns_error_and_stays_visible(api, name, make, status, code):
    bid, head = setup(api)
    r = send(api, bid, head, name, make())
    assert r.status_code == status, r.text
    b = r.json()
    assert b["error_code"] == code and b["message"] and b["submission_id"] and b["document_id"] is None
    m = manifest(api, bid, head)
    assert m["submissions"] == 1 and m["items"][0]["outcome"] == "rejected" and m["items"][0]["reason"] == code


@pytest.mark.parametrize("name,make,status,code", [
    ("a.pdf", lambda: image("PNG"), 415, "extension_content_mismatch"),
    ("a.pdf", lambda: pdf(1, js=True), 422, "active_content"),
    ("a.xml", lambda: b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>', 422, "unsafe_xml"),
])
def test_unsafe_files_quarantined(api, name, make, status, code):
    bid, head = setup(api)
    b = send(api, bid, head, name, make())
    assert b.status_code == status, b.text
    assert b.json()["error_code"] == code and b.json()["document_id"]
    assert manifest(api, bid, head)["items"][0]["status"] == "quarantined"


def test_too_large_is_not_read_and_recorded(api, monkeypatch):
    monkeypatch.setattr(safety, "MAX_BYTES", 10)
    bid, head = setup(api)
    r = send(api, bid, head, "a.xml", XML)
    assert r.status_code == 413 and r.json()["error_code"] == "file_too_large"
    assert manifest(api, bid, head)["items"][0]["sha256"] is None


def test_exactly_at_size_limit_accepted(api, monkeypatch):
    monkeypatch.setattr(safety, "MAX_BYTES", len(XML))
    bid, head = setup(api)
    assert send(api, bid, head, "a.xml", XML).status_code == 201


def test_missing_file_key_and_user(api):
    bid, head = setup(api)
    url = f"/batches/{bid}/documents"
    assert api.post(url, headers={**head, "Idempotency-Key": "k"}).json()["error_code"] == "empty_file"
    assert api.post(url, files={"file": ("a.xml", XML)}, headers=head).json()["error_code"] == "missing_idempotency_key"
    r = api.post(url, files={"file": ("a.xml", XML)}, headers={**head, "Idempotency-Key": "k" * 129})
    assert r.json()["error_code"] == "invalid_idempotency_key"
    r = api.post(url, files={"file": ("a.xml", XML)}, headers={"Idempotency-Key": "k"})
    assert r.status_code == 401 and r.json()["error_code"] == "unauthenticated"


# Gửi trùng (ING 05)
def test_replay_same_key(api):
    bid, head = setup(api)
    a = send(api, bid, head, "a.xml", XML, "k1")
    b = send(api, bid, head, "a.xml", XML, "k1")
    assert (a.status_code, b.status_code) == (201, 200)
    assert a.json()["submission_id"] == b.json()["submission_id"]
    assert a.json()["document_id"] == b.json()["document_id"] and b.json()["duplicate"] is True
    assert manifest(api, bid, head)["submissions"] == 1


def test_replay_of_rejected_returns_same_error(api):
    bid, head = setup(api)
    first = send(api, bid, head, "a.exe", b"MZ", "k1").json()
    second = send(api, bid, head, "a.exe", b"MZ", "k1").json()
    assert first == second and manifest(api, bid, head)["submissions"] == 1


def test_key_reused_for_other_file_conflicts(api):
    bid, head = setup(api)
    send(api, bid, head, "a.xml", XML, "k1")
    r = send(api, bid, head, "b.xml", XML + b" ", "k1")
    assert r.status_code == 409 and r.json()["error_code"] == "idempotency_key_conflict"


def test_same_file_new_key_links_existing_and_is_visible(api):
    bid, head = setup(api)
    a = send(api, bid, head, "a.xml", XML).json()
    b = send(api, bid, head, "copy.xml", XML)
    assert b.status_code == 200 and b.json()["document_id"] == a["document_id"] and b.json()["duplicate"] is True
    m = manifest(api, bid, head)
    assert m["by_outcome"] == {"accepted": 1, "duplicate": 1}


def test_duplicate_of_quarantined_stays_blocked(api):
    bid, head = setup(api)
    png = image("PNG")
    first = send(api, bid, head, "a.pdf", png).json()
    again = send(api, bid, head, "a.png", png)
    assert again.status_code == 422 and again.json()["document_id"] == first["document_id"]


def test_retry_after_crash_before_commit(api):
    bid, head = setup(api)
    with SessionLocal() as db:
        cid = db.scalar(select(main.Batch.client_id).where(main.Batch.id == bid))
    main.store.put(cid, hashlib.sha256(XML).hexdigest(), XML)  # file đã ghi nhưng database chưa có
    assert send(api, bid, head, "a.xml", XML).status_code == 201


def test_corrupted_store_is_not_silently_accepted(api):
    api_client = TestClient(main.app, raise_server_exceptions=False)
    bid, head = setup(api_client)
    with SessionLocal() as db:
        cid = db.scalar(select(main.Batch.client_id).where(main.Batch.id == bid))
    main.store.put(cid, hashlib.sha256(XML).hexdigest(), b"khac noi dung")
    assert send(api_client, bid, head, "a.xml", XML).status_code == 500


# Cách ly khách hàng
def test_same_file_in_other_client_is_separate(api):
    bid, head = setup(api)
    bid2, head2 = setup(api, "KH B", "0109876543")
    a = send(api, bid, head, "a.xml", XML, "k1")
    b = send(api, bid2, head2, "a.xml", XML, "k1")
    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["document_id"] != b.json()["document_id"]


def test_cross_client_is_hidden(api):
    bid, head = setup(api)
    doc = send(api, bid, head, "a.xml", XML).json()["document_id"]
    _, other = setup(api, "KH B", "0109876543")
    assert send(api, bid, other, "b.xml", XML).status_code == 404
    assert api.get(f"/documents/{doc}", headers=other).status_code == 404
    assert api.get(f"/batches/{bid}/manifest", headers=other).status_code == 404
    assert api.get(f"/documents/{uuid.uuid4()}", headers=head).status_code == 404


# Tên file an toàn
@pytest.mark.parametrize("raw,clean", [
    ("../../etc/a.xml", "a.xml"), ("C:\\x\\a.xml", "a.xml"), ("a\x00b.xml", "ab.xml"),
    ("", "unnamed"), ("hoa\u0301 đơn.xml", "ho\u00e1 đơn.xml"),
])
def test_clean_name(raw, clean):
    assert main.clean_name(raw) == clean


def test_mime_comes_from_content_not_client(api):
    bid, head = setup(api)
    r = api.post(f"/batches/{bid}/documents", files={"file": ("a.xml", XML, "application/pdf")},
                 headers={**head, "Idempotency-Key": "k"})
    assert r.json()["mime_type"] == "application/xml"


def test_originals_cannot_be_overwritten(tmp_path):
    s = LocalWriteOnceStore(str(tmp_path))
    s.put("c", "h", b"one")
    with pytest.raises(OriginalExists):
        s.put("c", "h", b"two")
    assert s.get("c/h") == b"one"


def test_state_machine_has_no_auto_approval():
    with pytest.raises(IllegalTransition):
        check_transition(State.PROCESSING, State.APPROVED)
    with pytest.raises(IllegalTransition):
        check_transition(State.QUARANTINED, State.PROCESSING)


def test_openapi_file_matches_code():
    from scripts.export_openapi import TARGET, render
    assert TARGET.read_text(encoding="utf-8") == render(), "Chạy lại: python -m scripts.export_openapi"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="cần PostgreSQL")
def test_concurrent_uploads_create_one_document(api):
    bid, head = setup(api)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: send(api, bid, head, "a.xml", XML), range(16)))
    assert sorted(r.status_code for r in results) == [200] * 15 + [201]
    assert len({r.json()["document_id"] for r in results}) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
    assert manifest(api, bid, head)["submissions"] == 16
