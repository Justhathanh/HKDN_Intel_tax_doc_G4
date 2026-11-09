import hashlib
import unicodedata
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import safety
from .auth import User, current_user, require_scope
from .db import get_db
from .errors import ApiError, api_error_handler
from .models import Batch, Client, Document, StateEvent, Submission
from .schemas import BatchIn, BatchOut, ClientIn, ClientOut, DocumentOut, DocumentReceipt, ErrorBody, Manifest
from .states import State
from .storage import LocalWriteOnceStore, OriginalExists

app = FastAPI(title="THTax Intelligent Tax Document Ingestion", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(ApiError, api_error_handler)
store = LocalWriteOnceStore()

ERR = {"model": ErrorBody}
UPLOAD_ERRORS = {s: ERR for s in (400, 401, 404, 409, 413, 415, 422)}


def _iso(value: datetime) -> str:
    if value.tzinfo is None:  # SQLite trả về thời gian không có múi giờ
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_name(name: str | None) -> str:
    """Bỏ đường dẫn và ký tự điều khiển; chuẩn NFC để giữ đúng dấu tiếng Việt."""
    base = unicodedata.normalize("NFC", (name or "").replace("\\", "/").rsplit("/", 1)[-1])
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Cc").strip()
    return base[-255:] or "unnamed"


def _batch_or_404(db: Session, user: User, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise ApiError("not_found")
    require_scope(user, batch.client_id)
    return batch


def _receipt(sub: Submission, doc: Document, duplicate: bool, status_code: int) -> JSONResponse:
    body = DocumentReceipt(
        document_id=doc.id, submission_id=sub.id, batch_id=sub.batch_id, file_name=sub.file_name,
        size=doc.size, sha256=doc.sha256, mime_type=doc.mime_type, page_count=doc.page_count,
        channel=sub.channel, uploaded_by=sub.actor, status=doc.status, duplicate=duplicate,
        received_at=_iso(sub.received_at))
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _read_limited(file: UploadFile) -> bytes | None:
    """Trả None nếu vượt giới hạn; không đọc file quá lớn vào bộ nhớ."""
    if file.size is not None and file.size > safety.MAX_BYTES:
        return None
    data = file.file.read(safety.MAX_BYTES + 1)
    return None if len(data) > safety.MAX_BYTES else data


def _save_original(client_id: str, digest: str, data: bytes) -> str:
    try:
        return store.put(client_id, digest, data)
    except OriginalExists as exc:  # lần trước đã ghi file nhưng chưa kịp commit database
        key = str(exc)
        if hashlib.sha256(store.get(key)).hexdigest() != digest:
            raise
        return key


def _replay(db: Session, prior: Submission, digest: str | None) -> JSONResponse:
    if prior.sha256 != digest:
        raise ApiError("idempotency_key_conflict", prior.id)
    if prior.outcome in ("rejected", "quarantined"):
        raise ApiError(prior.reason or "quarantined", prior.id, prior.document_id)
    return _receipt(prior, db.get(Document, prior.document_id), True, 200)


def _accept(db: Session, batch: Batch, user: User, key: str, name: str, data: bytes | None,
            digest: str | None, size: int, verdict: safety.Verdict) -> JSONResponse:
    prior = db.scalar(select(Submission).where(
        Submission.client_id == batch.client_id, Submission.idempotency_key == key))
    if prior is not None:
        return _replay(db, prior, digest)

    sub = Submission(client_id=batch.client_id, batch_id=batch.id, idempotency_key=key, file_name=name,
                     sha256=digest, size=size, actor=user.name, outcome="accepted")
    if not verdict.ok and not verdict.quarantine:
        sub.outcome, sub.reason = "rejected", verdict.reason
        db.add(sub)
        db.commit()
        raise ApiError(verdict.reason, sub.id)

    existing = db.scalar(select(Document).where(
        Document.client_id == batch.client_id, Document.sha256 == digest))
    if existing is not None:
        sub.document_id = existing.id
        if verdict.quarantine or existing.status == State.QUARANTINED:
            sub.outcome, sub.reason = "quarantined", verdict.reason or "quarantined"
            db.add(sub)
            db.commit()
            raise ApiError(sub.reason, sub.id, existing.id)
        sub.outcome, sub.reason = "duplicate", "same_hash_in_client"
        db.add(sub)
        db.commit()
        return _receipt(sub, existing, True, 200)

    doc = Document(client_id=batch.client_id, batch_id=batch.id, original_name=name,
                   mime_type=safety.MIME.get(verdict.kind or "", "application/octet-stream"),
                   size=size, page_count=verdict.page_count, sha256=digest,
                   storage_key=_save_original(batch.client_id, digest, data),
                   status=State.QUARANTINED if verdict.quarantine else State.RECEIVED,
                   uploaded_by=user.name)
    db.add(doc)
    db.flush()
    db.add(StateEvent(document_id=doc.id, from_state=None, to_state=doc.status, actor=user.name,
                      reason=verdict.reason or "upload"))
    sub.document_id = doc.id
    if verdict.quarantine:
        sub.outcome, sub.reason = "quarantined", verdict.reason
    db.add(sub)
    db.commit()
    if verdict.quarantine:
        raise ApiError(verdict.reason, sub.id, doc.id)
    return _receipt(sub, doc, False, 201)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/clients", status_code=201, response_model=ClientOut, responses={401: ERR})
def create_client(body: ClientIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    client = Client(name=body.name, tax_id=body.tax_id)
    db.add(client)
    db.commit()
    return ClientOut(id=client.id, name=client.name, tax_id=client.tax_id)


@app.post("/batches", status_code=201, response_model=BatchOut, responses={401: ERR, 404: ERR})
def create_batch(body: BatchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_scope(user, body.client_id)
    if db.get(Client, body.client_id) is None:
        raise ApiError("not_found")
    batch = Batch(client_id=body.client_id, engagement_id=body.engagement_id, created_by=user.name)
    db.add(batch)
    db.commit()
    return BatchOut(id=batch.id, client_id=batch.client_id, engagement_id=batch.engagement_id)


@app.post("/batches/{batch_id}/documents", status_code=201, response_model=DocumentReceipt,
          responses={200: {"model": DocumentReceipt, "description": "File đã có; trả Document ID cũ"}, **UPLOAD_ERRORS})
def upload_document(
    batch_id: str,
    file: Annotated[UploadFile | None, File(description="Một file PDF, JPG, PNG hoặc XML, tối đa 20 MiB")] = None,
    idempotency_key: Annotated[str | None, Header(description="Bắt buộc; UUID sinh cho mỗi lần chọn file")] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    batch = _batch_or_404(db, user, batch_id)
    if not idempotency_key:
        raise ApiError("missing_idempotency_key")
    if len(idempotency_key) > 128:
        raise ApiError("invalid_idempotency_key")
    if file is None:
        raise ApiError("empty_file")

    name = clean_name(file.filename)
    data = _read_limited(file)
    if data is None:
        size, digest = file.size or safety.MAX_BYTES + 1, None
        verdict = safety.Verdict(False, reason="file_too_large")
    else:
        size, digest = len(data), hashlib.sha256(data).hexdigest()
        verdict = safety.inspect(name, data)

    for attempt in (1, 2):
        try:
            return _accept(db, batch, user, idempotency_key, name, data, digest, size, verdict)
        except IntegrityError:  # hai request cùng file chạy đồng thời: lần sau đọc lại kết quả đã có
            db.rollback()
            if attempt == 2:
                raise


@app.get("/documents/{document_id}", response_model=DocumentOut, responses={401: ERR, 404: ERR})
def get_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("not_found")
    require_scope(user, doc.client_id)
    return DocumentOut(document_id=doc.id, batch_id=doc.batch_id, file_name=doc.original_name, size=doc.size,
                       sha256=doc.sha256, mime_type=doc.mime_type, page_count=doc.page_count, status=doc.status,
                       uploaded_by=doc.uploaded_by, received_at=_iso(doc.received_at))


@app.get("/batches/{batch_id}/manifest", response_model=Manifest, responses={401: ERR, 404: ERR})
def manifest(batch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    batch = _batch_or_404(db, user, batch_id)
    rows = db.execute(select(Submission, Document.status).outerjoin(Document, Submission.document_id == Document.id)
                      .where(Submission.batch_id == batch.id).order_by(Submission.received_at)).all()
    counts = dict(db.execute(select(Submission.outcome, func.count()).where(
        Submission.batch_id == batch.id).group_by(Submission.outcome)).all())
    return Manifest(batch_id=batch.id, submissions=len(rows), by_outcome=counts, items=[{
        "submission_id": s.id, "file_name": s.file_name, "size": s.size, "sha256": s.sha256, "outcome": s.outcome,
        "reason": s.reason, "document_id": s.document_id, "status": status, "uploaded_by": s.actor,
        "received_at": _iso(s.received_at)} for s, status in rows])
