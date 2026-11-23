"""Add tax entities and complete document-to-export domain schema.

Existing ingestion migrations are intentionally preserved. Legacy client.tax_id is
kept during this compatibility phase; each existing client is backfilled to one
TaxEntity and core records receive a nullable entity_id for staged API adoption.
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "0004_complete_tax_domain"
down_revision = "0003_job_state_checks"
branch_labels = None
depends_on = None


def _id():
    return str(uuid.uuid4())


def upgrade() -> None:
    op.create_table(
        "tax_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("tax_id", sa.String(20), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("representative_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "tax_id", name="uq_tax_entities_client_tax_id"),
        sa.UniqueConstraint("id", "client_id", name="uq_tax_entities_id_client"),
    )
    op.create_index("ix_tax_entities_client_id", "tax_entities", ["client_id"])

    bind = op.get_bind()
    clients = bind.execute(sa.text("SELECT id, name, tax_id FROM clients")).mappings().all()
    entity_by_client = {}
    for client in clients:
        entity_id = _id()
        bind.execute(
            sa.text("""INSERT INTO tax_entities
                (id, client_id, tax_id, legal_name, is_active, created_at)
                VALUES (:id, :client_id, :tax_id, :legal_name, TRUE, CURRENT_TIMESTAMP)"""),
            {"id": entity_id, "client_id": client["id"], "tax_id": client["tax_id"],
             "legal_name": client["name"]},
        )
        entity_by_client[client["id"]] = entity_id

    for table in ("batches", "documents", "submissions", "processing_jobs"):
        # Batch mode keeps the migration usable with SQLite development databases
        # as well as PostgreSQL production databases.
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("entity_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_entity_id_tax_entities", "tax_entities",
                ["entity_id"], ["id"]
            )
        op.create_index(f"ix_{table}_entity_id", table, ["entity_id"])

    for client_id, entity_id in entity_by_client.items():
        bind.execute(sa.text("UPDATE batches SET entity_id=:eid WHERE client_id=:cid"),
                     {"eid": entity_id, "cid": client_id})
        bind.execute(sa.text("UPDATE documents SET entity_id=:eid WHERE client_id=:cid"),
                     {"eid": entity_id, "cid": client_id})
        bind.execute(sa.text("UPDATE submissions SET entity_id=:eid WHERE client_id=:cid"),
                     {"eid": entity_id, "cid": client_id})
        bind.execute(sa.text("UPDATE processing_jobs SET entity_id=:eid WHERE client_id=:cid"),
                     {"eid": entity_id, "cid": client_id})

    op.create_table(
        "document_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("file_role", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_file_id", sa.String(36), sa.ForeignKey("document_files.id"), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.UniqueConstraint("document_id", "file_role", "version_no", name="uq_document_files_role_version"),
        sa.CheckConstraint("version_no >= 1", name="ck_document_files_version_positive"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_document_files_size_nonnegative"),
    )
    op.create_index("ix_document_files_client_id", "document_files", ["client_id"])
    op.create_index("ix_document_files_document_id", "document_files", ["document_id"])
    op.create_index("ix_document_files_document_role", "document_files", ["document_id", "file_role"])

    # Backfill original evidence metadata; file bytes remain in the existing storage backend.
    docs = bind.execute(sa.text("SELECT id, client_id, original_name, mime_type, size, sha256, storage_key, uploaded_by, received_at FROM documents")).mappings().all()
    for doc in docs:
        bind.execute(sa.text("""INSERT INTO document_files
            (id, client_id, document_id, file_role, storage_key, file_name, mime_type,
             size_bytes, sha256, version_no, created_by, created_at)
            VALUES (:id, :client_id, :document_id, 'original', :storage_key, :file_name,
             :mime_type, :size_bytes, :sha256, 1, :created_by, :created_at)"""),
            {"id": _id(), "client_id": doc["client_id"], "document_id": doc["id"],
             "storage_key": doc["storage_key"], "file_name": doc["original_name"],
             "mime_type": doc["mime_type"], "size_bytes": doc["size"], "sha256": doc["sha256"],
             "created_by": doc["uploaded_by"], "created_at": doc["received_at"]})

    op.create_table(
        "processing_job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("processing_jobs.id"), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processing_job_events_job_id", "processing_job_events", ["job_id"])
    op.create_index("ix_job_events_job_created", "processing_job_events", ["job_id", "created_at"])

    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("processing_jobs.id"), nullable=True),
        sa.Column("extractor_name", sa.String(64), nullable=False),
        sa.Column("extractor_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_extraction_runs_client_id", "extraction_runs", ["client_id"])
    op.create_index("ix_extraction_runs_document_id", "extraction_runs", ["document_id"])
    op.create_index("ix_extraction_runs_document_created", "extraction_runs", ["document_id", "started_at"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("tax_entities.id"), nullable=False),
        sa.Column("invoice_key", sa.String(255), nullable=False),
        sa.Column("invoice_number", sa.String(64), nullable=True),
        sa.Column("invoice_series", sa.String(64), nullable=True),
        sa.Column("template_code", sa.String(32), nullable=True),
        sa.Column("invoice_type", sa.String(64), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("subtotal", sa.Numeric(20, 4), nullable=True),
        sa.Column("tax_total", sa.Numeric(20, 4), nullable=True),
        sa.Column("grand_total", sa.Numeric(20, 4), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "entity_id", "invoice_key", name="uq_invoices_tenant_entity_key"),
        sa.CheckConstraint("grand_total IS NULL OR grand_total >= 0", name="ck_invoices_grand_total_nonnegative"),
    )
    op.create_index("ix_invoices_client_id", "invoices", ["client_id"])
    op.create_index("ix_invoices_entity_id", "invoices", ["entity_id"])
    op.create_index("ix_invoices_client_entity_issue_date", "invoices", ["client_id", "entity_id", "issue_date"])

    def simple_table(name, columns, indexes=()):
        op.create_table(name, sa.Column("id", sa.String(36), primary_key=True), *columns)
        for idx_name, cols in indexes:
            op.create_index(idx_name, name, cols)

    simple_table("invoice_parties", [
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("party_role", sa.String(16), nullable=False),
        sa.Column("tax_id", sa.String(20)), sa.Column("legal_name", sa.String(255)),
        sa.Column("address", sa.Text()), sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(32)), sa.Column("bank_account", sa.String(64)),
        sa.Column("bank_name", sa.String(255)),
        sa.UniqueConstraint("invoice_id", "party_role", name="uq_invoice_party_role"),
    ], [("ix_invoice_parties_invoice_id", ["invoice_id"])])

    simple_table("invoice_lines", [
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False), sa.Column("item_code", sa.String(64)),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("unit", sa.String(32)),
        sa.Column("quantity", sa.Numeric(20, 4)), sa.Column("unit_price", sa.Numeric(20, 4)),
        sa.Column("amount", sa.Numeric(20, 4)), sa.Column("tax_rate", sa.String(16)),
        sa.Column("tax_amount", sa.Numeric(20, 4)),
        sa.UniqueConstraint("invoice_id", "line_no", name="uq_invoice_lines_number"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_invoice_lines_quantity_nonnegative"),
    ], [("ix_invoice_lines_invoice_id", ["invoice_id"])])

    simple_table("invoice_taxes", [
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("tax_rate", sa.String(16), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(20, 4)), sa.Column("tax_amount", sa.Numeric(20, 4)),
    ], [("ix_invoice_taxes_invoice_id", ["invoice_id"])])

    simple_table("invoice_documents", [
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("relation_type", sa.String(24), nullable=False, server_default="source"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("linked_by", sa.String(128)), sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("invoice_id", "document_id", name="uq_invoice_documents_link"),
    ], [("ix_invoice_documents_invoice_id", ["invoice_id"]), ("ix_invoice_documents_document_id", ["document_id"])])

    simple_table("extracted_fields", [
        sa.Column("extraction_run_id", sa.String(36), sa.ForeignKey("extraction_runs.id"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("field_name", sa.String(128), nullable=False), sa.Column("raw_value", sa.Text()),
        sa.Column("normalized_value", sa.Text()), sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("source_anchor", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], [("ix_extracted_fields_extraction_run_id", ["extraction_run_id"]), ("ix_extracted_fields_invoice_id", ["invoice_id"]), ("ix_extracted_fields_run_name", ["extraction_run_id", "field_name"])])

    simple_table("field_validations", [
        sa.Column("extracted_field_id", sa.String(36), sa.ForeignKey("extracted_fields.id"), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message", sa.Text()), sa.Column("expected_value", sa.Text()), sa.Column("actual_value", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], [("ix_field_validations_extracted_field_id", ["extracted_field_id"]), ("ix_field_validations_field", ["extracted_field_id", "created_at"])])

    simple_table("document_validations", [
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("validation_scope", sa.String(24), nullable=False), sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("message", sa.Text()),
        sa.Column("details", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], [("ix_document_validations_document_id", ["document_id"])])

    simple_table("review_cases", [
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id")),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("assigned_to", sa.String(128)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    ], [("ix_review_cases_client_id", ["client_id"]), ("ix_review_cases_document_id", ["document_id"]), ("ix_review_cases_invoice_id", ["invoice_id"]), ("ix_review_cases_status_created", ["status", "created_at"])])

    simple_table("review_changes", [
        sa.Column("review_case_id", sa.String(36), sa.ForeignKey("review_cases.id"), nullable=False),
        sa.Column("extracted_field_id", sa.String(36), sa.ForeignKey("extracted_fields.id")),
        sa.Column("field_name", sa.String(128), nullable=False), sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], [("ix_review_changes_review_case_id", ["review_case_id"]), ("ix_review_changes_extracted_field_id", ["extracted_field_id"])])

    simple_table("approval_records", [
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id")),
        sa.Column("decision", sa.String(16), nullable=False), sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text()), sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    ], [("ix_approval_records_client_id", ["client_id"]), ("ix_approval_records_document_id", ["document_id"]), ("ix_approval_records_invoice_id", ["invoice_id"])])

    simple_table("audit_logs", [
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(64), nullable=False), sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(64)), sa.Column("before_data", sa.JSON()), sa.Column("after_data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], [("ix_audit_logs_client_id", ["client_id"]), ("ix_audit_logs_tenant_created", ["client_id", "created_at"])])

    simple_table("export_jobs", [
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("tax_entities.id"), nullable=False),
        sa.Column("export_format", sa.String(24), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.String(128), nullable=False), sa.Column("storage_key", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
    ], [("ix_export_jobs_client_id", ["client_id"]), ("ix_export_jobs_entity_id", ["entity_id"]), ("ix_export_jobs_tenant_status", ["client_id", "status"])])

    simple_table("export_items", [
        sa.Column("export_job_id", sa.String(36), sa.ForeignKey("export_jobs.id"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.String(128)),
        sa.UniqueConstraint("export_job_id", "invoice_id", name="uq_export_items_invoice"),
    ], [("ix_export_items_export_job_id", ["export_job_id"]), ("ix_export_items_invoice_id", ["invoice_id"])])


def downgrade() -> None:
    for table in (
        "export_items", "export_jobs", "audit_logs", "approval_records", "review_changes",
        "review_cases", "document_validations", "field_validations", "extracted_fields",
        "invoice_documents", "invoice_taxes", "invoice_lines", "invoice_parties", "invoices",
        "extraction_runs", "processing_job_events", "document_files",
    ):
        op.drop_table(table)
    for table in ("processing_jobs", "submissions", "documents", "batches"):
        op.drop_index(f"ix_{table}_entity_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_entity_id_tax_entities", type_="foreignkey")
            batch.drop_column("entity_id")
    op.drop_index("ix_tax_entities_client_id", table_name="tax_entities")
    op.drop_table("tax_entities")
