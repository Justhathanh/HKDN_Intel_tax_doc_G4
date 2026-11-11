"""G4T-18: giới hạn dung lượng 20 MiB, kiểm tra đúng tại biên. Toàn bộ là dữ liệu giả."""
import uuid

from sqlalchemy import func, select

from app import safety
from app.db import SessionLocal
from app.models import Document

MIB_20 = 20 * 1024 * 1024


def xml_of_size(size: int) -> bytes:
    head, tail = b"<HDon>", b"</HDon>"
    return head + b" " * (size - len(head) - len(tail)) + tail


def setup(api):
    head = {"X-User": "u1"}
    cid = api.post("/clients", json={"name": "KH A", "tax_id": "0312345678"}, headers=head).json()["id"]
    head["X-Client-Ids"] = cid
    bid = api.post("/batches", json={"client_id": cid, "engagement_id": "E1"}, headers=head).json()["id"]
    return bid, head


def send(api, bid, head, data):
    return api.post(f"/batches/{bid}/documents", files={"file": ("a.xml", data)},
                    headers={**head, "Idempotency-Key": str(uuid.uuid4())})


def documents() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Document))


def test_limit_is_20_mib():
    assert safety.MAX_BYTES == MIB_20 == 20_971_520


def test_exactly_20_mib_accepted(api):
    bid, head = setup(api)
    r = send(api, bid, head, xml_of_size(MIB_20))
    assert r.status_code == 201, r.text[:200]
    assert r.json()["size"] == MIB_20 and documents() == 1


def test_one_byte_over_rejected_with_clear_error(api):
    bid, head = setup(api)
    r = send(api, bid, head, xml_of_size(MIB_20 + 1))
    assert r.status_code == 413
    body = r.json()
    assert body["error_code"] == "file_too_large" and "20 MiB" in body["message"] and body["document_id"] is None
    assert documents() == 0


def test_oversized_upload_stays_visible_in_manifest(api):
    bid, head = setup(api)
    send(api, bid, head, xml_of_size(MIB_20 + 1))
    m = api.get(f"/batches/{bid}/manifest", headers=head).json()
    assert m["submissions"] == 1 and m["by_outcome"] == {"rejected": 1}
    item = m["items"][0]
    assert item["reason"] == "file_too_large" and item["sha256"] is None and item["size"] == MIB_20 + 1


def test_small_file_not_affected(api):
    bid, head = setup(api)
    assert send(api, bid, head, xml_of_size(100)).status_code == 201
