"""Mô hình dữ liệu tiếp nhận (DAT 01, một phần DAT 02). Thiết kế: docs/G4T-10-thiet-ke-api-upload.md"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(255))
    tax_id: Mapped[str] = mapped_column(String(20))  # luôn là chuỗi, giữ số 0 đầu


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    engagement_id: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    """Một file gốc duy nhất trong phạm vi một khách hàng."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("client_id", "sha256", name="uq_documents_client_sha256"),
        Index("ix_documents_status", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int]
    page_count: Mapped[int | None]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32))
    uploaded_by: Mapped[str] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Submission(Base):
    """Mỗi lần gửi là một bản ghi, kể cả file bị từ chối hoặc gửi trùng (ING 02, ING 05)."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("client_id", "idempotency_key", name="uq_submissions_client_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int]
    channel: Mapped[str] = mapped_column(String(32), default="browser")
    actor: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(32))  # accepted | duplicate | rejected | quarantined
    reason: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StateEvent(Base):
    __tablename__ = "state_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProcessingJob(Base):
    """Một lần thử xử lý nền cho một tài liệu (ARC 02, DAT 04). Thiết kế: docs/G4T-66-thiet-ke-processing-job.md

    Mỗi dòng là một lần thử; thử lại tạo dòng mới với attempt_no + 1 và cùng correlation_id,
    nên lịch sử từng lần thử không bị ghi đè.
    """

    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("document_id", "job_type", "attempt_no", name="uq_jobs_document_type_attempt"),
        # G4T-67: database cũng từ chối trạng thái lạ và số lần thử sai, kể cả khi ai đó sửa thẳng bằng SQL.
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter')",
                        name="ck_jobs_status"),
        CheckConstraint("attempt_no >= 1 AND attempt_no <= max_attempts", name="ck_jobs_attempt_range"),
        Index("ix_jobs_status_next_attempt", "status", "next_attempt_at"),
        # Mỗi tài liệu chỉ có tối đa một job đang chờ hoặc đang chạy cho mỗi loại việc.
        Index("uq_jobs_one_active", "document_id", "job_type", unique=True,
              postgresql_where=text("status IN ('queued', 'running')"),
              sqlite_where=text("status IN ('queued', 'running')")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)  # job_id
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    attempt_no: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    retry_of_job_id: Mapped[str | None] = mapped_column(ForeignKey("processing_jobs.id"))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    processor_version: Mapped[str | None] = mapped_column(String(64))
    locked_by: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(300))
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)
