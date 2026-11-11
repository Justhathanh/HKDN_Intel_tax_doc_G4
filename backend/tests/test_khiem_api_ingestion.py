"""Bộ kiểm thử API tiếp nhận tài liệu (CV13 - G4T-14 / G4T-21)."""
import hashlib
import io
import uuid

from pypdf import PdfWriter

from app import safety


def _make_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(100, 100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _create_client_and_batch(api) -> tuple[str, dict[str, str]]:
    headers = {"X-User": "kim"}
    client_res = api.post(
        "/clients",
        json={"name": "Cty_Test_Khiem", "tax_id": "0312345678"},
        headers=headers,
    )
    assert client_res.status_code == 201
    client_id = client_res.json()["id"]
    headers["X-Client-Ids"] = client_id
    batch_res = api.post(
        "/batches",
        json={"client_id": client_id, "engagement_id": "T11-2026"},
        headers=headers,
    )
    assert batch_res.status_code == 201
    return batch_res.json()["id"], headers


def test_upload_valid_pdf_returns_receipt_and_sha256(api):
    batch_id, headers = _create_client_and_batch(api)
    data = _make_pdf(2)
    r = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("valid_2p.pdf", data, "application/pdf")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "received"
    assert body["duplicate"] is False
    assert body["page_count"] == 2
    assert body["sha256"] == hashlib.sha256(data).hexdigest()


def test_upload_missing_idempotency_key(api):
    batch_id, headers = _create_client_and_batch(api)
    r = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("a.pdf", _make_pdf(1), "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "missing_idempotency_key"


def test_upload_duplicate_idempotency_key(api):
    batch_id, headers = _create_client_and_batch(api)
    data = _make_pdf(1)
    key = str(uuid.uuid4())
    first = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("a.pdf", data, "application/pdf")},
        headers={**headers, "Idempotency-Key": key},
    )
    second = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("a.pdf", data, "application/pdf")},
        headers={**headers, "Idempotency-Key": key},
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["document_id"] == first.json()["document_id"]


def test_get_document_and_manifest_after_upload(api):
    batch_id, headers = _create_client_and_batch(api)
    data = _make_pdf(1)
    up = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("a.pdf", data, "application/pdf")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    doc_id = up.json()["document_id"]

    doc_res = api.get(f"/documents/{doc_id}", headers=headers)
    assert doc_res.status_code == 200
    assert doc_res.json()["sha256"] == hashlib.sha256(data).hexdigest()

    man_res = api.get(f"/batches/{batch_id}/manifest", headers=headers)
    assert man_res.status_code == 200
    assert man_res.json()["submissions"] == 1
    assert man_res.json()["by_outcome"] == {"accepted": 1}


def test_unauthorized_client_scope_returns_404(api):
    _, headers = _create_client_and_batch(api)
    other_client = api.post(
        "/clients",
        json={"name": "Cty_Khac", "tax_id": "0109998888"},
        headers={"X-User": "kim"},
    ).json()["id"]
    r = api.post(
        "/batches",
        json={"client_id": other_client, "engagement_id": "T11-2026"},
        headers=headers,
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "not_found"


def test_upload_over_max_bytes_returns_413(api):
    batch_id, headers = _create_client_and_batch(api)
    oversized = b"%PDF-1.4\n" + b"0" * (safety.MAX_BYTES + 1 - 9)
    r = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("over_20mb.pdf", oversized, "application/pdf")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 413
    assert r.json()["error_code"] == "file_too_large"


def test_upload_over_30_pages_returns_422(api):
    batch_id, headers = _create_client_and_batch(api)
    r = api.post(
        f"/batches/{batch_id}/documents",
        files={"file": ("over_30p.pdf", _make_pdf(31), "application/pdf")},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "too_many_pages"
