"""Vòng đời của processing job, chính sách retry, dead-letter và lịch sử chạy (G4T-66, G4T-67, G4T-73..76).
Thiết kế: docs/G4T-66-thiet-ke-processing-job.md, docs/G4T-67-state-machine-job.md, docs/G4T-73-chinh-sach-retry-dlq.md

Module này chỉ quản lý trạng thái job. Việc đổi trạng thái tài liệu (received -> processing ...)
thuộc worker và vẫn phải đi qua states.check_transition.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from .models import Document, ProcessingJob
from .states import State
from .storage import LocalWriteOnceStore

DEFAULT_MAX_ATTEMPTS = 3
BACKOFF_BASE = timedelta(seconds=30)
BACKOFF_MAX = timedelta(minutes=15)
DEFAULT_LEASE = timedelta(minutes=10)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


# State machine của MỘT dòng job (G4T-67). Thử lại không đưa dòng cũ về queued mà tạo dòng mới
# (attempt_no + 1), nên failed vẫn là trạng thái cuối của dòng đó.
JOB_ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING}),
    JobStatus.RUNNING: frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.DEAD_LETTER}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.DEAD_LETTER: frozenset(),
}
ACTIVE_JOB_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})
TERMINAL_JOB_STATUSES = frozenset(s for s, targets in JOB_ALLOWED.items() if not targets)

# Lý do bị chặn, dùng cho thông báo lỗi và tài liệu.
_BLOCKED_REASON = {
    JobStatus.QUEUED: "job chưa được worker nhận, chỉ có thể chuyển sang running",
    JobStatus.RUNNING: "job đang chạy chỉ kết thúc bằng succeeded, failed hoặc dead_letter",
    JobStatus.SUCCEEDED: "succeeded là trạng thái cuối; muốn chạy lại phải tạo job mới",
    JobStatus.FAILED: "failed là trạng thái cuối của lần thử này; lần thử lại là một dòng job mới",
    JobStatus.DEAD_LETTER: "dead_letter là trạng thái cuối; cần người xem xét trước khi tạo job mới",
}

# Chỉ lưu mã lỗi và câu thông báo trong danh sách này, không bao giờ lưu nội dung exception:
# exception có thể chứa chữ trong tài liệu, đường dẫn hoặc thông tin cấu hình (SEC 04).
SAFE_ERRORS: dict[str, tuple[bool, str]] = {
    "original_missing": (False, "Không tìm thấy bản gốc trong kho lưu trữ."),
    "original_tampered": (False, "Mã băm bản gốc không khớp; dừng xử lý."),
    "unsupported_document": (False, "Loại tài liệu chưa được hỗ trợ."),
    "parser_error": (False, "Không đọc được cấu trúc tài liệu."),
    # G4T-61: lỗi parse XML (app/xml_parser.py), đều không thử lại vì file không đổi
    "xml_unsafe": (False, "XML có DTD, entity hoặc tham chiếu ngoài; không xử lý."),
    "xml_malformed": (False, "XML sai cú pháp, không đọc được."),
    "xml_unsupported_variant": (False, "XML không thuộc chuẩn hóa đơn nào đang hỗ trợ."),
    "xml_schema_invalid": (False, "XML thiếu phần bắt buộc của chuẩn hóa đơn."),
    "ocr_timeout": (True, "Dịch vụ OCR phản hồi quá thời gian."),
    "ocr_unavailable": (True, "Dịch vụ OCR tạm thời không dùng được."),
    "quota_exceeded": (True, "Đã chạm hạn mức của dịch vụ xử lý."),
    "lease_expired": (True, "Worker không báo kết quả trước khi hết hạn giữ việc."),
    "internal_error": (True, "Lỗi nội bộ khi xử lý."),
}

RETRYABLE_ERRORS: frozenset[str] = frozenset(code for code, (retryable, _) in SAFE_ERRORS.items() if retryable)
NON_RETRYABLE_ERRORS: frozenset[str] = frozenset(code for code, (retryable, _) in SAFE_ERRORS.items() if not retryable)


class IllegalJobTransition(ValueError):
    pass


class JobError(Exception):
    """Worker ném lỗi này với một mã trong SAFE_ERRORS."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code if code in SAFE_ERRORS else "internal_error"


class NotProcessable(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# G4T-68: giao diện hiển thị 4 trạng thái như Jira G4T-39; dead_letter hiện là FAILED và will_retry = False.
DISPLAY_STATUS: dict[JobStatus, str] = {
    JobStatus.QUEUED: "QUEUED",
    JobStatus.RUNNING: "RUNNING",
    JobStatus.SUCCEEDED: "SUCCEEDED",
    JobStatus.FAILED: "FAILED",
    JobStatus.DEAD_LETTER: "FAILED",
}


def is_terminal(status: str) -> bool:
    return JobStatus(status) in TERMINAL_JOB_STATUSES


def check_job_transition(current: str, target: str) -> None:
    """Chặn mọi chuyển trạng thái không có trong JOB_ALLOWED, kể cả giá trị lạ và chuyển về chính nó."""
    try:
        source, dest = JobStatus(current), JobStatus(target)
    except ValueError as exc:
        raise IllegalJobTransition(f"trạng thái không hợp lệ: {current} -> {target}") from exc
    if dest not in JOB_ALLOWED[source]:
        raise IllegalJobTransition(f"{source} -> {dest}: {_BLOCKED_REASON[source]}")


def safe_error(code: str) -> tuple[str, bool, str]:
    """Trả (mã, có thử lại được không, thông báo) chỉ từ danh sách cho phép."""
    code = code if code in SAFE_ERRORS else "internal_error"
    retryable, message = SAFE_ERRORS[code]
    return code, retryable, message


def backoff(attempt_no: int) -> timedelta:
    return min(BACKOFF_BASE * (2 ** (attempt_no - 1)), BACKOFF_MAX)


def retry_policy() -> dict:
    """Trả về cấu hình chính sách retry hiện hành (G4T-73)."""
    return {
        "default_max_attempts": DEFAULT_MAX_ATTEMPTS,
        "backoff_base_seconds": int(BACKOFF_BASE.total_seconds()),
        "backoff_max_seconds": int(BACKOFF_MAX.total_seconds()),
        "default_lease_seconds": int(DEFAULT_LEASE.total_seconds()),
        "retryable_errors": sorted(RETRYABLE_ERRORS),
        "non_retryable_errors": sorted(NON_RETRYABLE_ERRORS),
    }


def duration_ms(job: ProcessingJob) -> int | None:
    """Tính thời lượng xử lý (ms) giữa started_at và finished_at cho lịch sử chạy (G4T-76)."""
    if job.started_at is None or job.finished_at is None:
        return None
    delta = _aware(job.finished_at) - _aware(job.started_at)
    return max(0, int(delta.total_seconds() * 1000))


def active_job(db: Session, document_id: str, job_type: str) -> ProcessingJob | None:
    return db.scalar(select(ProcessingJob).where(
        ProcessingJob.document_id == document_id, ProcessingJob.job_type == job_type,
        ProcessingJob.status.in_(ACTIVE_JOB_STATUSES)))


def enqueue(db: Session, document: Document, job_type: str = "extract", correlation_id: str | None = None,
            max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> ProcessingJob:
    """Tạo job cho tài liệu; gọi lại khi đã có job đang chờ hoặc đang chạy thì trả job đó."""
    if document.status in (State.QUARANTINED, State.REJECTED):
        raise NotProcessable(document.status)
    existing = active_job(db, document.id, job_type)
    if existing is not None:
        return existing
    last = db.scalar(select(ProcessingJob.attempt_no).where(
        ProcessingJob.document_id == document.id, ProcessingJob.job_type == job_type)
        .order_by(ProcessingJob.attempt_no.desc()).limit(1)) or 0
    next_attempt = last + 1
    job = ProcessingJob(client_id=document.client_id, document_id=document.id, job_type=job_type,
                        status=JobStatus.QUEUED, attempt_no=next_attempt,
                        max_attempts=max(max_attempts, next_attempt),
                        correlation_id=correlation_id or str(uuid.uuid4()), input_sha256=document.sha256)
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session, worker_id: str, job_type: str = "extract", now: datetime | None = None,
               lease: timedelta = DEFAULT_LEASE) -> ProcessingJob | None:
    """Worker nhận job đến hạn sớm nhất; SKIP LOCKED để hai worker không nhận cùng một job."""
    now = now or _now()
    job = db.scalar(select(ProcessingJob).where(
        ProcessingJob.status == JobStatus.QUEUED, ProcessingJob.job_type == job_type,
        ProcessingJob.next_attempt_at <= now)
        .order_by(ProcessingJob.next_attempt_at, ProcessingJob.created_at).limit(1)
        .with_for_update(skip_locked=True))
    if job is None:
        return None
    check_job_transition(job.status, JobStatus.RUNNING)
    job.status, job.locked_by, job.started_at, job.lease_expires_at = JobStatus.RUNNING, worker_id, now, now + lease
    db.flush()
    return job


def read_original(store: LocalWriteOnceStore, db: Session, job: ProcessingJob) -> bytes:
    """Đọc bản gốc ở chế độ chỉ đọc và kiểm tra mã băm trước khi xử lý (ING 04)."""
    document = db.get(Document, job.document_id)
    try:
        data = store.get(document.storage_key)
    except FileNotFoundError as exc:
        raise JobError("original_missing") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != job.input_sha256 or digest != document.sha256:
        raise JobError("original_tampered")
    return data


def succeed(db: Session, job: ProcessingJob, processor_version: str, now: datetime | None = None) -> None:
    check_job_transition(job.status, JobStatus.SUCCEEDED)
    job.status, job.processor_version, job.finished_at = JobStatus.SUCCEEDED, processor_version, now or _now()
    job.locked_by = job.lease_expires_at = None
    db.flush()


def fail(db: Session, job: ProcessingJob, code: str, processor_version: str | None = None,
         now: datetime | None = None) -> ProcessingJob | None:
    """Ghi lỗi an toàn; nếu còn lượt và lỗi thử lại được thì tạo lần thử mới, ngược lại chuyển dead_letter."""
    now = now or _now()
    code, retryable, message = safe_error(code)
    will_retry = retryable and job.attempt_no < job.max_attempts
    target = JobStatus.FAILED if will_retry else JobStatus.DEAD_LETTER
    check_job_transition(job.status, target)
    job.status, job.finished_at, job.processor_version = target, now, processor_version or job.processor_version
    job.error_code, job.error_retryable, job.error_message = code, retryable, message
    job.locked_by = job.lease_expires_at = None
    db.flush()
    if not will_retry:
        return None
    retry = ProcessingJob(client_id=job.client_id, document_id=job.document_id, job_type=job.job_type,
                          status=JobStatus.QUEUED, attempt_no=job.attempt_no + 1, max_attempts=job.max_attempts,
                          retry_of_job_id=job.id, correlation_id=job.correlation_id, input_sha256=job.input_sha256,
                          next_attempt_at=now + backoff(job.attempt_no))
    db.add(retry)
    db.flush()
    return retry


def reclaim_expired(db: Session, now: datetime | None = None) -> list[ProcessingJob]:
    """Job đang chạy mà worker mất kết nối quá hạn giữ việc thì ghi lỗi lease_expired và thử lại (ARC 02)."""
    now = now or _now()
    stale = db.scalars(select(ProcessingJob).where(
        ProcessingJob.status == JobStatus.RUNNING, ProcessingJob.lease_expires_at < now)
        .with_for_update(skip_locked=True)).all()
    retries = []
    for job in stale:
        retry = fail(db, job, "lease_expired", now=now)
        if retry is not None:
            retries.append(retry)
    return retries


def retry_dead_letter(db: Session, job: ProcessingJob, correlation_id: str | None = None,
                      now: datetime | None = None) -> tuple[ProcessingJob, bool]:
    """Tạo lần thử mới từ một job ở trạng thái dead_letter (G4T-74, G4T-75).

    Trả về (job_kết_quả, vừa_tạo_mới). Nếu đã có job đang chờ/chạy cho tài liệu này thì trả về luôn job đó
    để tránh xử lý trùng lặp khi người dùng bấm thử lại nhiều lần.
    """
    existing = active_job(db, job.document_id, job.job_type)
    if existing is not None:
        return existing, False
    if job.status != JobStatus.DEAD_LETTER:
        raise IllegalJobTransition(f"chỉ có thể thử lại job ở trạng thái dead_letter (hiện tại: {job.status})")

    last = db.scalar(select(ProcessingJob.attempt_no).where(
        ProcessingJob.document_id == job.document_id, ProcessingJob.job_type == job.job_type)
        .order_by(ProcessingJob.attempt_no.desc()).limit(1)) or job.attempt_no
    if last > job.attempt_no:
        raise IllegalJobTransition("đã tồn tại lần thử mới hơn cho tài liệu này")

    document = db.get(Document, job.document_id)
    if document is None or document.status in (State.QUARANTINED, State.REJECTED):
        raise NotProcessable(document.status if document else "missing_document")

    next_attempt = last + 1
    retry = ProcessingJob(
        client_id=job.client_id,
        document_id=job.document_id,
        job_type=job.job_type,
        status=JobStatus.QUEUED,
        attempt_no=next_attempt,
        max_attempts=max(job.max_attempts, next_attempt),
        retry_of_job_id=job.id,
        correlation_id=correlation_id or job.correlation_id,
        input_sha256=document.sha256,
        next_attempt_at=now or _now(),
    )
    db.add(retry)
    db.flush()
    return retry, True


def list_dead_letter_jobs(db: Session, client_ids: set[str], unresolved_only: bool = True,
                          limit: int = 50, offset: int = 0) -> tuple[list[ProcessingJob], int]:
    """Lấy danh sách job nằm trong Dead Letter Queue thuộc phạm vi client_ids được cấp quyền (G4T-75)."""
    if not client_ids:
        return [], 0
    newer = aliased(ProcessingJob)
    stmt = select(ProcessingJob).where(
        ProcessingJob.client_id.in_(client_ids),
        ProcessingJob.status == JobStatus.DEAD_LETTER,
    )
    if unresolved_only:
        stmt = stmt.where(
            ~exists(
                select(newer.id).where(
                    newer.document_id == ProcessingJob.document_id,
                    newer.job_type == ProcessingJob.job_type,
                    newer.attempt_no > ProcessingJob.attempt_no,
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ProcessingJob.finished_at.desc(), ProcessingJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), total


def list_document_jobs(db: Session, document_id: str, job_type: str | None = None) -> list[ProcessingJob]:
    """Trả về toàn bộ lịch sử các lần chạy job của một tài liệu theo thứ tự attempt_no (G4T-76)."""
    stmt = select(ProcessingJob).where(ProcessingJob.document_id == document_id)
    if job_type is not None:
        stmt = stmt.where(ProcessingJob.job_type == job_type)
    return list(db.scalars(stmt.order_by(ProcessingJob.attempt_no.asc(), ProcessingJob.created_at.asc())).all())
