"""Tax-domain and downstream processing models.

These tables extend the original ingestion schema without replacing its history.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric,
    String, Text, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaxEntity(Base):
    __tablename__ = "tax_entities"
    __table_args__ = (
        UniqueConstraint("client_id", "tax_id", name="uq_tax_entities_client_tax_id"),
        UniqueConstraint("id", "client_id", name="uq_tax_entities_id_client"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    tax_id: Mapped[str] = mapped_column(String(20), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    representative_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class DocumentFile(Base):
    """Metadata for immutable originals and derived working artifacts; bytes live in object storage."""
    __tablename__ = "document_files"
    __table_args__ = (
        UniqueConstraint("document_id", "file_role", "version_no", name="uq_document_files_role_version"),
        CheckConstraint("version_no >= 1", name="ck_document_files_version_positive"),
        CheckConstraint("size_bytes >= 0", name="ck_document_files_size_nonnegative"),
        Index("ix_document_files_document_role", "document_id", "file_role"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    file_role: Mapped[str] = mapped_column(String(32), nullable=False)  # original|working|preprocessed|page_image|thumbnail
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_file_id: Mapped[str | None] = mapped_column(ForeignKey("document_files.id"))
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)


class ProcessingJobEvent(Base):
    """Technical execution history. state_events remains the document business-state history."""
    __tablename__ = "processing_job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("processing_jobs.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (Index("ix_extraction_runs_document_created", "document_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("processing_jobs.id"))
    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # running|succeeded|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("client_id", "entity_id", "invoice_key", name="uq_invoices_tenant_entity_key"),
        CheckConstraint("grand_total IS NULL OR grand_total >= 0", name="ck_invoices_grand_total_nonnegative"),
        Index("ix_invoices_client_entity_issue_date", "client_id", "entity_id", "issue_date"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("tax_entities.id"), nullable=False, index=True)
    invoice_key: Mapped[str] = mapped_column(String(255), nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    invoice_series: Mapped[str | None] = mapped_column(String(64))
    template_code: Mapped[str | None] = mapped_column(String(32))
    invoice_type: Mapped[str | None] = mapped_column(String(64))
    issue_date: Mapped[datetime | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="VND", nullable=False)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class InvoiceParty(Base):
    __tablename__ = "invoice_parties"
    __table_args__ = (UniqueConstraint("invoice_id", "party_role", name="uq_invoice_party_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    party_role: Mapped[str] = mapped_column(String(16), nullable=False)  # seller|buyer
    tax_id: Mapped[str | None] = mapped_column(String(20))
    legal_name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    bank_name: Mapped[str | None] = mapped_column(String(255))


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_no", name="uq_invoice_lines_number"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_invoice_lines_quantity_nonnegative"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    tax_rate: Mapped[str | None] = mapped_column(String(16))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))


class InvoiceTax(Base):
    __tablename__ = "invoice_taxes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    tax_rate: Mapped[str] = mapped_column(String(16), nullable=False)
    taxable_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))


class InvoiceDocument(Base):
    __tablename__ = "invoice_documents"
    __table_args__ = (UniqueConstraint("invoice_id", "document_id", name="uq_invoice_documents_link"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(24), default="source", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    linked_by: Mapped[str | None] = mapped_column(String(128))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (Index("ix_extracted_fields_run_name", "extraction_run_id", "field_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    extraction_run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id"), nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source_anchor: Mapped[dict | None] = mapped_column(JSON)  # page, bbox or XML path
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FieldValidation(Base):
    __tablename__ = "field_validations"
    __table_args__ = (Index("ix_field_validations_field", "extracted_field_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    extracted_field_id: Mapped[str] = mapped_column(ForeignKey("extracted_fields.id"), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # passed|warning|failed
    message: Mapped[str | None] = mapped_column(Text)
    expected_value: Mapped[str | None] = mapped_column(Text)
    actual_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class DocumentValidation(Base):
    __tablename__ = "document_validations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    validation_scope: Mapped[str] = mapped_column(String(24), nullable=False)  # whole_document|cross_document
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ReviewCase(Base):
    __tablename__ = "review_cases"
    __table_args__ = (Index("ix_review_cases_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewChange(Base):
    __tablename__ = "review_changes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    review_case_id: Mapped[str] = mapped_column(ForeignKey("review_cases.id"), nullable=False, index=True)
    extracted_field_id: Mapped[str | None] = mapped_column(ForeignKey("extracted_fields.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved|rejected
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_tenant_created", "client_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (Index("ix_export_jobs_tenant_status", "client_id", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("tax_entities.id"), nullable=False, index=True)
    export_format: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class ExportItem(Base):
    __tablename__ = "export_items"
    __table_args__ = (UniqueConstraint("export_job_id", "invoice_id", name="uq_export_items_invoice"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    export_job_id: Mapped[str] = mapped_column(ForeignKey("export_jobs.id"), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128))
