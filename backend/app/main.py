import hashlib
import unicodedata
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import jobs, safety
from .auth import User, current_user, require_scope
from .db import get_db
from .errors import ApiError, api_error_handler
from .models import Batch, Client, Document, ProcessingJob, StateEvent, Submission
from .schemas import (
    BatchIn,
    BatchOut,
    ClientIn,
    ClientOut,
    DeadLetterListOut,
    DocumentOut,
    DocumentReceipt,
    ErrorBody,
    JobErrorOut,
    JobList,
    JobOut,
    Manifest,
    RetryPolicyOut,
)
from .states import State
from .storage import LocalWriteOnceStore, OriginalExists

app = FastAPI(title="THTax Intelligent Tax Document Ingestion", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(ApiError, api_error_handler)
store = LocalWriteOnceStore()

# Mô tả viết tường minh để đặc tả không đổi theo phiên bản Python
_ERROR_DESCRIPTIONS = {
    400: "Yêu cầu không hợp lệ", 401: "Chưa xác thực", 404: "Không tìm thấy hoặc không có quyền",
    409: "Idempotency-Key đã dùng cho file khác", 413: "File quá lớn", 415: "Định dạng không được hỗ trợ",
    422: "File không xử lý được",
}


def _errors(*codes: int) -> dict:
    return {c: {"model": ErrorBody, "description": _ERROR_DESCRIPTIONS[c]} for c in codes}


UPLOAD_ERRORS = _errors(400, 401, 404, 409, 413, 415, 422)


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
    else:
        jobs.enqueue(db, doc)
    db.add(sub)
    db.commit()
    if verdict.quarantine:
        raise ApiError(verdict.reason, sub.id, doc.id)
    return _receipt(sub, doc, False, 201)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/retry-policy", response_model=RetryPolicyOut, responses=_errors(401))
def get_retry_policy(_: User = Depends(current_user)) -> RetryPolicyOut:
    return RetryPolicyOut(**jobs.retry_policy())


@app.post("/clients", status_code=201, response_model=ClientOut, responses=_errors(401))
def create_client(body: ClientIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    client = Client(name=body.name, tax_id=body.tax_id)
    db.add(client)
    db.commit()
    return ClientOut(id=client.id, name=client.name, tax_id=client.tax_id)


@app.post("/batches", status_code=201, response_model=BatchOut, responses=_errors(401, 404))
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


@app.get("/documents/{document_id}", response_model=DocumentOut, responses=_errors(401, 404))
def get_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("not_found")
    require_scope(user, doc.client_id)
    return DocumentOut(document_id=doc.id, batch_id=doc.batch_id, file_name=doc.original_name, size=doc.size,
                       sha256=doc.sha256, mime_type=doc.mime_type, page_count=doc.page_count, status=doc.status,
                       uploaded_by=doc.uploaded_by, received_at=_iso(doc.received_at))


@app.get("/batches/{batch_id}/manifest", response_model=Manifest, responses=_errors(401, 404))
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


def _iso_or_none(value: datetime | None) -> str | None:
    return _iso(value) if value is not None else None


def _duration_ms(job: ProcessingJob) -> int | None:
    """Thời lượng một lần thử, tính từ started_at đến finished_at (dùng cho lịch sử chạy, G4T-76)."""
    if job.started_at is None or job.finished_at is None:
        return None
    started = job.started_at if job.started_at.tzinfo else job.started_at.replace(tzinfo=timezone.utc)
    finished = job.finished_at if job.finished_at.tzinfo else job.finished_at.replace(tzinfo=timezone.utc)
    return max(0, int((finished - started).total_seconds() * 1000))


def _job_out(job: ProcessingJob) -> JobOut:
    status = jobs.JobStatus(job.status)
    error = None
    if job.error_code:
        error = JobErrorOut(code=job.error_code, message=job.error_message or "", retryable=bool(job.error_retryable))
    return JobOut(
        job_id=job.id, document_id=job.document_id, job_type=job.job_type, status=status,
        display_status=jobs.DISPLAY_STATUS[status], will_retry=status == jobs.JobStatus.FAILED,
        attempt_no=job.attempt_no, max_attempts=job.max_attempts, retry_of_job_id=job.retry_of_job_id,
        correlation_id=job.correlation_id, processor_version=job.processor_version,
        created_at=_iso(job.created_at), next_attempt_at=_iso(job.next_attempt_at),
        started_at=_iso_or_none(job.started_at), finished_at=_iso_or_none(job.finished_at),
        duration_ms=_duration_ms(job), error=error)


@app.get("/jobs/dead-letter", response_model=DeadLetterListOut, responses=_errors(401))
def list_dead_letter(
    unresolved_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows, total = jobs.list_dead_letter_jobs(
        db, user.client_ids, unresolved_only=unresolved_only, limit=limit, offset=offset
    )
    return DeadLetterListOut(total=total, items=[_job_out(j) for j in rows])


@app.get("/jobs/{job_id}", response_model=JobOut, responses=_errors(401, 404))
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Trạng thái một lần thử xử lý. Job của khách hàng khác trả 404 như không tồn tại."""
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise ApiError("not_found")
    require_scope(user, job.client_id)
    return _job_out(job)


@app.post(
    "/jobs/{job_id}/retry",
    status_code=201,
    response_model=JobOut,
    responses={
        200: {"model": JobOut, "description": "Job đang chờ hoặc đang chạy"},
        **_errors(401, 404),
        409: {"model": ErrorBody, "description": "Job không ở trạng thái có thể thử lại"},
        **_errors(422),
    },
)
def retry_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    # TODO (SEC 01): Bổ sung kiểm tra phân quyền vai trò (chỉ accountant_lead / admin được retry thủ công) theo G4T-68 mục 9.
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise ApiError("not_found")
    require_scope(user, job.client_id)
    try:
        retried, created = jobs.retry_dead_letter(db, job)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = jobs.active_job(db, job.document_id, job.job_type)
        if existing is None:
            raise
        retried, created = existing, False
    except jobs.IllegalJobTransition as exc:
        raise ApiError("job_not_retryable", document_id=job.document_id) from exc
    except jobs.NotProcessable as exc:
        raise ApiError("quarantined", document_id=job.document_id) from exc

    return JSONResponse(status_code=201 if created else 200, content=_job_out(retried).model_dump())


@app.get("/documents/{document_id}/jobs", response_model=JobList, responses=_errors(401, 404))
def list_document_jobs(document_id: str, job_type: str = "extract", db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    """Lịch sử các lần thử của một tài liệu, cũ trước mới sau; latest là lần thử mới nhất."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("not_found")
    require_scope(user, doc.client_id)
    rows = db.scalars(select(ProcessingJob).where(
        ProcessingJob.document_id == doc.id, ProcessingJob.job_type == job_type)
        .order_by(ProcessingJob.attempt_no)).all()
    items = [_job_out(job) for job in rows]
    return JobList(document_id=doc.id, latest=items[-1] if items else None, items=items)