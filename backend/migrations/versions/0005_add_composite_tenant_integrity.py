
"""Add composite tenant integrity constraints.

Revision ID: 01b3a304aabc
Revises: 0004_complete_tax_domain
"""

from alembic import op
import sqlalchemy as sa


revision = "01b3a304aabc"
down_revision = "0004_complete_tax_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # 1. CREATE UNIQUE CONSTRAINTS FIRST
    #    These constraints are required by composite foreign keys.
    # ============================================================

    # Batches
    op.create_unique_constraint(
        "uq_batches_id_client",
        "batches",
        ["id", "client_id"],
    )
    op.create_unique_constraint(
        "uq_batches_id_client_entity",
        "batches",
        ["id", "client_id", "entity_id"],
    )

    # Documents
    op.create_unique_constraint(
        "uq_documents_id_client",
        "documents",
        ["id", "client_id"],
    )
    op.create_unique_constraint(
        "uq_documents_id_client_entity",
        "documents",
        ["id", "client_id", "entity_id"],
    )

    # Invoices
    op.create_unique_constraint(
        "uq_invoices_id_client",
        "invoices",
        ["id", "client_id"],
    )
    op.create_unique_constraint(
        "uq_invoices_id_client_entity",
        "invoices",
        ["id", "client_id", "entity_id"],
    )

    # Export jobs
    op.create_unique_constraint(
        "uq_export_jobs_id_client_entity",
        "export_jobs",
        ["id", "client_id", "entity_id"],
    )

    # ============================================================
    # 2. ADD NEW COLUMNS
    # ============================================================

    op.add_column(
        "export_items",
        sa.Column("client_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "export_items",
        sa.Column("entity_id", sa.String(length=36), nullable=True),
    )

    op.create_index(
        op.f("ix_export_items_client_id"),
        "export_items",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_export_items_entity_id"),
        "export_items",
        ["entity_id"],
        unique=False,
    )

    op.add_column(
        "invoice_documents",
        sa.Column("client_id", sa.String(length=36), nullable=True),
    )

    op.create_index(
        op.f("ix_invoice_documents_client_id"),
        "invoice_documents",
        ["client_id"],
        unique=False,
    )

    # ============================================================
    # 3. BACKFILL EXISTING DATA
    # ============================================================

    # ExportItem inherits client_id/entity_id from ExportJob.
    op.execute("""
        UPDATE export_items AS ei
        SET
            client_id = ej.client_id,
            entity_id = ej.entity_id
        FROM export_jobs AS ej
        WHERE ei.export_job_id = ej.id
    """)

    # InvoiceDocument inherits client_id from Invoice.
    op.execute("""
        UPDATE invoice_documents AS idoc
        SET client_id = i.client_id
        FROM invoices AS i
        WHERE idoc.invoice_id = i.id
    """)

    # ============================================================
    # 4. VALIDATE BACKFILLED DATA
    #    Raise an exception instead of silently accepting invalid
    #    tenant/entity relationships.
    # ============================================================

    op.execute("""
        DO $$
        BEGIN
            -- Every ExportItem must have tenant/entity information.
            IF EXISTS (
                SELECT 1
                FROM export_items
                WHERE client_id IS NULL
                   OR entity_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Migration failed: export_items has missing client_id/entity_id';
            END IF;

            -- ExportItem must belong to the same tenant/entity
            -- as both its ExportJob and Invoice.
            IF EXISTS (
                SELECT 1
                FROM export_items ei
                JOIN export_jobs ej
                    ON ej.id = ei.export_job_id
                JOIN invoices i
                    ON i.id = ei.invoice_id
                WHERE ei.client_id IS DISTINCT FROM ej.client_id
                   OR ei.entity_id IS DISTINCT FROM ej.entity_id
                   OR ei.client_id IS DISTINCT FROM i.client_id
                   OR ei.entity_id IS DISTINCT FROM i.entity_id
            ) THEN
                RAISE EXCEPTION
                    'Migration failed: export_items tenant/entity mismatch';
            END IF;

            -- Every InvoiceDocument must have a client_id.
            IF EXISTS (
                SELECT 1
                FROM invoice_documents
                WHERE client_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Migration failed: invoice_documents has missing client_id';
            END IF;

            -- Invoice and Document must belong to the same tenant.
            IF EXISTS (
                SELECT 1
                FROM invoice_documents idoc
                JOIN invoices i
                    ON i.id = idoc.invoice_id
                JOIN documents d
                    ON d.id = idoc.document_id
                WHERE idoc.client_id IS DISTINCT FROM i.client_id
                   OR idoc.client_id IS DISTINCT FROM d.client_id
            ) THEN
                RAISE EXCEPTION
                    'Migration failed: invoice_documents tenant mismatch';
            END IF;
        END $$;
    """)

    # ============================================================
    # 5. MAKE NEW COLUMNS NOT NULL
    # ============================================================

    op.alter_column(
        "export_items",
        "client_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.alter_column(
        "export_items",
        "entity_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.alter_column(
        "invoice_documents",
        "client_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )

    # ============================================================
    # 6. APPROVAL RECORDS
    # ============================================================


    op.drop_constraint(
        "approval_records_document_id_fkey",
        "approval_records",
        type_="foreignkey",
    )

    op.drop_constraint(
        "approval_records_invoice_id_fkey",
        "approval_records",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_approval_records_document_client",
        "approval_records",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )

    op.create_foreign_key(
        "fk_approval_records_invoice_client",
        "approval_records",
        "invoices",
        ["invoice_id", "client_id"],
        ["id", "client_id"],
    )
    # ============================================================
    # 7. BATCHES
    # ============================================================

    op.drop_constraint(
        "fk_batches_entity_id_tax_entities",
        "batches",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_batches_entity_client",
        "batches",
        "tax_entities",
        ["entity_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 8. DOCUMENT FILES
    # ============================================================

    op.drop_constraint(
        "document_files_document_id_fkey",
        "document_files",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_document_files_document_client",
        "document_files",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 9. DOCUMENTS
    # ============================================================

    op.drop_constraint(
        "fk_documents_entity_id_tax_entities",
        "documents",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_documents_entity_client",
        "documents",
        "tax_entities",
        ["entity_id", "client_id"],
        ["id", "client_id"],
    )

    # Replace legacy document -> batch FK
    op.drop_constraint(
        "documents_batch_id_fkey",
        "documents",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_documents_batch_client",
        "documents",
        "batches",
        ["batch_id", "client_id"],
        ["id", "client_id"],
    )

    op.create_foreign_key(
        "fk_documents_batch_client_entity",
        "documents",
        "batches",
        ["batch_id", "client_id", "entity_id"],
        ["id", "client_id", "entity_id"],
    )

    # ============================================================
    # 10. EXPORT ITEMS
    # ============================================================

    op.drop_constraint(
        "export_items_invoice_id_fkey",
        "export_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "export_items_export_job_id_fkey",
        "export_items",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_export_items_client",
        "export_items",
        "clients",
        ["client_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_export_items_job_tenant_entity",
        "export_items",
        "export_jobs",
        ["export_job_id", "client_id", "entity_id"],
        ["id", "client_id", "entity_id"],
    )

    op.create_foreign_key(
        "fk_export_items_invoice_tenant_entity",
        "export_items",
        "invoices",
        ["invoice_id", "client_id", "entity_id"],
        ["id", "client_id", "entity_id"],
    )

    # ============================================================
    # 11. EXPORT JOBS
    # ============================================================

    op.drop_constraint(
        "export_jobs_entity_id_fkey",
        "export_jobs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_export_jobs_entity_client",
        "export_jobs",
        "tax_entities",
        ["entity_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 12. EXTRACTION RUNS
    # ============================================================

    op.drop_index(
        "ix_extraction_runs_document_created",
        table_name="extraction_runs",
    )

    op.create_index(
        "ix_extraction_runs_document_started",
        "extraction_runs",
        ["document_id", "started_at"],
        unique=False,
    )

    op.drop_constraint(
        "extraction_runs_document_id_fkey",
        "extraction_runs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_extraction_runs_document_client",
        "extraction_runs",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 13. INVOICE DOCUMENTS
    # ============================================================

    op.drop_constraint(
        "invoice_documents_invoice_id_fkey",
        "invoice_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "invoice_documents_document_id_fkey",
        "invoice_documents",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_invoice_documents_client",
        "invoice_documents",
        "clients",
        ["client_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_invoice_documents_document_client",
        "invoice_documents",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )

    op.create_foreign_key(
        "fk_invoice_documents_invoice_client",
        "invoice_documents",
        "invoices",
        ["invoice_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 14. INVOICES
    # ============================================================

    op.drop_constraint(
        "invoices_entity_id_fkey",
        "invoices",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_invoices_entity_client",
        "invoices",
        "tax_entities",
        ["entity_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 15. PROCESSING JOBS
    # ============================================================

    op.drop_constraint(
        "processing_jobs_document_id_fkey",
        "processing_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_processing_jobs_entity_id_tax_entities",
        "processing_jobs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_processing_jobs_document_client",
        "processing_jobs",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )
    op.create_foreign_key(
        "fk_processing_jobs_entity_client",
        "processing_jobs",
        "tax_entities",
        ["entity_id", "client_id"],
        ["id", "client_id"],
    )
    op.create_foreign_key(
        "fk_processing_jobs_document_client_entity",
        "processing_jobs",
        "documents",
        ["document_id", "client_id", "entity_id"],
        ["id", "client_id", "entity_id"],
    )

    # ============================================================
    # 16. REVIEW CASES
    # ============================================================

    op.drop_constraint(
        "review_cases_invoice_id_fkey",
        "review_cases",
        type_="foreignkey",
    )
    op.drop_constraint(
        "review_cases_document_id_fkey",
        "review_cases",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_review_cases_document_client",
        "review_cases",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )
    op.create_foreign_key(
        "fk_review_cases_invoice_client",
        "review_cases",
        "invoices",
        ["invoice_id", "client_id"],
        ["id", "client_id"],
    )

    # ============================================================
    # 17. SUBMISSIONS
    # ============================================================

    op.drop_constraint(
        "submissions_batch_id_fkey",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "submissions_document_id_fkey",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_entity_id_tax_entities",
        "submissions",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_submissions_batch_client_entity",
        "submissions",
        "batches",
        ["batch_id", "client_id", "entity_id"],
        ["id", "client_id", "entity_id"],
    )
    op.create_foreign_key(
        "fk_submissions_batch_client",
        "submissions",
        "batches",
        ["batch_id", "client_id"],
        ["id", "client_id"],
    )
    op.create_foreign_key(
        "fk_submissions_document_client",
        "submissions",
        "documents",
        ["document_id", "client_id"],
        ["id", "client_id"],
    )
    op.create_foreign_key(
        "fk_submissions_entity_client",
        "submissions",
        "tax_entities",
        ["entity_id", "client_id"],
        ["id", "client_id"],
    )
    op.create_foreign_key(
        "fk_submissions_document_client_entity",
        "submissions",
        "documents",
        ["document_id", "client_id", "entity_id"],
        ["id", "client_id", "entity_id"],
    )


def downgrade() -> None:
    # ============================================================
    # 1. SUBMISSIONS
    # ============================================================

    op.drop_constraint(
        "fk_submissions_document_client_entity",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_entity_client",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_document_client",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_batch_client",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_batch_client_entity",
        "submissions",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_submissions_entity_id_tax_entities",
        "submissions",
        "tax_entities",
        ["entity_id"],
        ["id"],
    )
    op.create_foreign_key(
        "submissions_document_id_fkey",
        "submissions",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "submissions_batch_id_fkey",
        "submissions",
        "batches",
        ["batch_id"],
        ["id"],
    )

    # ============================================================
    # 2. REVIEW CASES
    # ============================================================

    op.drop_constraint(
        "fk_review_cases_invoice_client",
        "review_cases",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_review_cases_document_client",
        "review_cases",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "review_cases_document_id_fkey",
        "review_cases",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "review_cases_invoice_id_fkey",
        "review_cases",
        "invoices",
        ["invoice_id"],
        ["id"],
    )

    # ============================================================
    # 3. PROCESSING JOBS
    # ============================================================

    op.drop_constraint(
        "fk_processing_jobs_document_client_entity",
        "processing_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_processing_jobs_entity_client",
        "processing_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_processing_jobs_document_client",
        "processing_jobs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_processing_jobs_entity_id_tax_entities",
        "processing_jobs",
        "tax_entities",
        ["entity_id"],
        ["id"],
    )
    op.create_foreign_key(
        "processing_jobs_document_id_fkey",
        "processing_jobs",
        "documents",
        ["document_id"],
        ["id"],
    )

    # ============================================================
    # 4. INVOICES
    # ============================================================

    op.drop_constraint(
        "fk_invoices_entity_client",
        "invoices",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "invoices_entity_id_fkey",
        "invoices",
        "tax_entities",
        ["entity_id"],
        ["id"],
    )

    # ============================================================
    # 5. INVOICE DOCUMENTS
    # ============================================================

    op.drop_constraint(
        "fk_invoice_documents_invoice_client",
        "invoice_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_invoice_documents_document_client",
        "invoice_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_invoice_documents_client",
        "invoice_documents",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "invoice_documents_document_id_fkey",
        "invoice_documents",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "invoice_documents_invoice_id_fkey",
        "invoice_documents",
        "invoices",
        ["invoice_id"],
        ["id"],
    )

    op.drop_index(
        op.f("ix_invoice_documents_client_id"),
        table_name="invoice_documents",
    )
    op.drop_column("invoice_documents", "client_id")

    # ============================================================
    # 6. EXTRACTION RUNS
    # ============================================================

    op.drop_constraint(
        "fk_extraction_runs_document_client",
        "extraction_runs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "extraction_runs_document_id_fkey",
        "extraction_runs",
        "documents",
        ["document_id"],
        ["id"],
    )

    op.drop_index(
        "ix_extraction_runs_document_started",
        table_name="extraction_runs",
    )

    op.create_index(
        "ix_extraction_runs_document_created",
        "extraction_runs",
        ["document_id", "started_at"],
        unique=False,
    )

    # ============================================================
    # 7. EXPORT JOBS
    # ============================================================

    op.drop_constraint(
        "fk_export_jobs_entity_client",
        "export_jobs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "export_jobs_entity_id_fkey",
        "export_jobs",
        "tax_entities",
        ["entity_id"],
        ["id"],
    )

    # ============================================================
    # 8. EXPORT ITEMS
    # ============================================================

    op.drop_constraint(
        "fk_export_items_invoice_tenant_entity",
        "export_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_export_items_job_tenant_entity",
        "export_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_export_items_client",
        "export_items",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "export_items_export_job_id_fkey",
        "export_items",
        "export_jobs",
        ["export_job_id"],
        ["id"],
    )
    op.create_foreign_key(
        "export_items_invoice_id_fkey",
        "export_items",
        "invoices",
        ["invoice_id"],
        ["id"],
    )

    op.drop_index(
        op.f("ix_export_items_entity_id"),
        table_name="export_items",
    )
    op.drop_index(
        op.f("ix_export_items_client_id"),
        table_name="export_items",
    )

    op.drop_column("export_items", "entity_id")
    op.drop_column("export_items", "client_id")

    # ============================================================
    # 9. DOCUMENTS
    # ============================================================

    op.drop_constraint(
        "fk_documents_batch_client_entity",
        "documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_documents_entity_client",
        "documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_documents_batch_client",
        "documents",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_documents_entity_id_tax_entities",
        "documents",
        "tax_entities",
        ["entity_id"],
        ["id"],
    )
    op.create_foreign_key(
        "documents_batch_id_fkey",
        "documents",
        "batches",
        ["batch_id"],
        ["id"],
    )

        # Drop dependent composite foreign keys first
    op.drop_constraint(
        "fk_document_files_document_client",
        "document_files",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_approval_records_document_client",
        "approval_records",
        type_="foreignkey",
    )

    # Drop composite unique constraints
    op.drop_constraint(
        "uq_documents_id_client_entity",
        "documents",
        type_="unique",
    )

    op.drop_constraint(
        "uq_documents_id_client",
        "documents",
        type_="unique",
    )

    # ============================================================
    # 10. DOCUMENT FILES
    # ============================================================

    op.create_foreign_key(
        "document_files_document_id_fkey",
        "document_files",
        "documents",
        ["document_id"],
        ["id"],
    )

    # ============================================================
    # 11. BATCHES
    # ============================================================

    op.drop_constraint(
        "fk_batches_entity_client",
        "batches",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_batches_entity_id_tax_entities",
        "batches",
        "tax_entities",
        ["entity_id"],
        ["id"],
    )

    op.drop_constraint(
        "uq_batches_id_client_entity",
        "batches",
        type_="unique",
    )
    op.drop_constraint(
        "uq_batches_id_client",
        "batches",
        type_="unique",
    )

    # ============================================================
    # 12. APPROVAL RECORDS
    # ============================================================

    op.drop_constraint(
        "fk_approval_records_invoice_client",
        "approval_records",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "approval_records_invoice_id_fkey",
        "approval_records",
        "invoices",
        ["invoice_id"],
        ["id"],
    )
    op.create_foreign_key(
        "approval_records_document_id_fkey",
        "approval_records",
        "documents",
        ["document_id"],
        ["id"],
    )
    # ============================================================
    # 13. DROP INVOICE UNIQUE CONSTRAINTS LAST
    # ============================================================

    op.drop_constraint(
        "uq_invoices_id_client_entity",
        "invoices",
        type_="unique",
    )
    op.drop_constraint(
        "uq_invoices_id_client",
        "invoices",
        type_="unique",
    )

    # ============================================================
    # 14. DROP EXPORT JOB UNIQUE CONSTRAINT
    # ============================================================

    op.drop_constraint(
        "uq_export_jobs_id_client_entity",
        "export_jobs",
        type_="unique",
    )
