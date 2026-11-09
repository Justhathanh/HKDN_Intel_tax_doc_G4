"""Mô hình dữ liệu tiếp nhận (DAT 01, một phần DAT 02). Thiết kế: docs/G4T-10-thiet-ke-api-upload.md"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
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
