"""Mô hình dữ liệu tiếp nhận (DAT 01, một phần DAT 02). Thiết kế: docs/G4T-10-thiet-ke-api-upload.md"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    text,
    Text,
    UniqueConstraint,
)

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

    __table_args__ = (
        UniqueConstraint(
            "id", "client_id",
            name="uq_batches_id_client",
        ),
        UniqueConstraint(
            "id", "client_id", "entity_id",
            name="uq_batches_id_client_entity",
        ),
        ForeignKeyConstraint(
            ["entity_id", "client_id"],
            ["tax_entities.id", "tax_entities.client_id"],
            name="fk_batches_entity_client",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_id
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(36), index=True
    )
    engagement_id: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class Document(Base):
    """Một file gốc duy nhất trong phạm vi một khách hàng."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "sha256",
            name="uq_documents_client_sha256"
        ),
        UniqueConstraint(
            "id", "client_id",
            name="uq_documents_id_client"
        ),
        UniqueConstraint(
            "id", "client_id", "entity_id",
            name="uq_documents_id_client_entity"
        ),
        ForeignKeyConstraint(
            ["entity_id", "client_id"],
            ["tax_entities.id", "tax_entities.client_id"],
            name="fk_documents_entity_client"
        ),
        ForeignKeyConstraint(
            ["batch_id", "client_id", "entity_id"],
            ["batches.id", "batches.client_id", "batches.entity_id"],
            name="fk_documents_batch_client_entity"
        ),
        ForeignKeyConstraint(
            ["batch_id", "client_id"],
            ["batches.id", "batches.client_id"],
            name="fk_documents_batch_client"
),
        Index("ix_documents_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True
    )
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int]
    page_count: Mapped[int | None]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32))
    uploaded_by: Mapped[str] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class Submission(Base):
    """Mỗi lần gửi là một bản ghi, kể cả file bị từ chối hoặc gửi trùng."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "idempotency_key",
            name="uq_submissions_client_key"
        ),
        ForeignKeyConstraint(
            ["entity_id", "client_id"],
            ["tax_entities.id", "tax_entities.client_id"],
            name="fk_submissions_entity_client"
        ),
        ForeignKeyConstraint(
            ["batch_id", "client_id"],
            ["batches.id", "batches.client_id"],
            name="fk_submissions_batch_client"
        ),
        ForeignKeyConstraint(
            ["batch_id", "client_id", "entity_id"],
            ["batches.id", "batches.client_id", "batches.entity_id"],
            name="fk_submissions_batch_client_entity"
        ),
        ForeignKeyConstraint(
            ["document_id", "client_id"],
            ["documents.id", "documents.client_id"],
            name="fk_submissions_document_client"
        ),
        ForeignKeyConstraint(
            ["document_id", "client_id", "entity_id"],
            ["documents.id", "documents.client_id", "documents.entity_id"],
            name="fk_submissions_document_client_entity"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True
    )
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int]
    channel: Mapped[str] = mapped_column(String(32), default="browser")
    actor: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


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
    """Một lần thử xử lý nền cho một tài liệu."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "job_type", "attempt_no",
            name="uq_jobs_document_type_attempt"
        ),
        ForeignKeyConstraint(
            ["document_id", "client_id"],
            ["documents.id", "documents.client_id"],
            name="fk_processing_jobs_document_client"
        ),
        ForeignKeyConstraint(
            ["document_id", "client_id", "entity_id"],
            ["documents.id", "documents.client_id", "documents.entity_id"],
            name="fk_processing_jobs_document_client_entity"
        ),
        ForeignKeyConstraint(
            ["entity_id", "client_id"],
            ["tax_entities.id", "tax_entities.client_id"],
            name="fk_processing_jobs_entity_client"
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter')",
            name="ck_jobs_status"
        ),
        CheckConstraint(
            "attempt_no >= 1 AND attempt_no <= max_attempts",
            name="ck_jobs_attempt_range"
        ),
        Index("ix_jobs_status_next_attempt", "status", "next_attempt_at"),
        Index(
            "uq_jobs_one_active",
            "document_id", "job_type",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')")
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_id
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True
    )
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    attempt_no: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    retry_of_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("processing_jobs.id")
    )
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    processor_version: Mapped[str | None] = mapped_column(String(64))
    locked_by: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(300))
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)

# Register downstream tax-domain models in shared SQLAlchemy metadata.
from . import domain_models as _domain_models  # noqa: E402,F401
