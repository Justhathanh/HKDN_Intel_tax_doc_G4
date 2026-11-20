
import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, engine
from app.models import Batch, Client, Document
from app.domain_models import (
    ApprovalRecord,
    DocumentFile,
    ExtractionRun,
    ExportItem,
    ExportJob,
    Invoice,
    InvoiceDocument,
    ReviewCase,
    TaxEntity,
)


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Composite tenant integrity tests require PostgreSQL",
)


@pytest.fixture
def tenant_data(api):
    """Create two isolated tenants with entities, batches, documents and invoices."""

    with SessionLocal() as db:
        client_a = Client(name="Tenant A", tax_id="TEST000001")
        client_b = Client(name="Tenant B", tax_id="TEST000002")
        db.add_all([client_a, client_b])
        db.flush()

        entity_a = TaxEntity(
            client_id=client_a.id,
            tax_id="ENTITY0001",
            legal_name="Entity A",
        )
        entity_b = TaxEntity(
            client_id=client_b.id,
            tax_id="ENTITY0002",
            legal_name="Entity B",
        )
        db.add_all([entity_a, entity_b])
        db.flush()

        batch_a = Batch(
            client_id=client_a.id,
            entity_id=entity_a.id,
            engagement_id="ENG-A",
            created_by="test",
        )
        batch_b = Batch(
            client_id=client_b.id,
            entity_id=entity_b.id,
            engagement_id="ENG-B",
            created_by="test",
        )
        db.add_all([batch_a, batch_b])
        db.flush()

        document_a = Document(
            client_id=client_a.id,
            entity_id=entity_a.id,
            batch_id=batch_a.id,
            original_name="tenant-a.pdf",
            mime_type="application/pdf",
            size=100,
            page_count=1,
            sha256="a" * 64,
            storage_key="tenant-a/original.pdf",
            status="uploaded",
            uploaded_by="test",
        )
        document_b = Document(
            client_id=client_b.id,
            entity_id=entity_b.id,
            batch_id=batch_b.id,
            original_name="tenant-b.pdf",
            mime_type="application/pdf",
            size=100,
            page_count=1,
            sha256="b" * 64,
            storage_key="tenant-b/original.pdf",
            status="uploaded",
            uploaded_by="test",
        )
        db.add_all([document_a, document_b])
        db.flush()

        invoice_a = Invoice(
            client_id=client_a.id,
            entity_id=entity_a.id,
            invoice_key="INV-A-001",
        )
        invoice_b = Invoice(
            client_id=client_b.id,
            entity_id=entity_b.id,
            invoice_key="INV-B-001",
        )
        db.add_all([invoice_a, invoice_b])
        db.commit()

        return {
            "client_a": client_a.id,
            "client_b": client_b.id,
            "entity_a": entity_a.id,
            "entity_b": entity_b.id,
            "document_a": document_a.id,
            "document_b": document_b.id,
            "invoice_a": invoice_a.id,
            "invoice_b": invoice_b.id,
        }


def test_document_file_rejects_document_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        db.add(
            DocumentFile(
                client_id=data["client_a"],
                document_id=data["document_b"],
                file_role="original",
                storage_key="test/cross-tenant-file.pdf",
                file_name="cross-tenant-file.pdf",
                mime_type="application/pdf",
                size_bytes=100,
                sha256="c" * 64,
                version_no=1,
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_extraction_run_rejects_document_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        db.add(
            ExtractionRun(
                client_id=data["client_a"],
                document_id=data["document_b"],
                extractor_name="test-extractor",
                status="completed",
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_invoice_document_rejects_cross_tenant_document(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        db.add(
            InvoiceDocument(
                client_id=data["client_a"],
                invoice_id=data["invoice_a"],
                document_id=data["document_b"],
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_review_case_rejects_invoice_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        db.add(
            ReviewCase(
                client_id=data["client_a"],
                document_id=data["document_a"],
                invoice_id=data["invoice_b"],
                status="pending",
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_approval_record_rejects_invoice_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        db.add(
            ApprovalRecord(
                client_id=data["client_a"],
                document_id=data["document_a"],
                invoice_id=data["invoice_b"],
                decision="approved",
                actor="test-user",
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_export_job_rejects_entity_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        db.add(
            ExportJob(
                client_id=data["client_a"],
                entity_id=data["entity_b"],
                export_format="xml",
                status="queued",
                requested_by="test-user",
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_export_item_rejects_invoice_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        export_job = ExportJob(
            client_id=data["client_a"],
            entity_id=data["entity_a"],
            export_format="xml",
            status="queued",
            requested_by="test-user",
        )
        db.add(export_job)
        db.flush()

        db.add(
            ExportItem(
                client_id=data["client_a"],
                entity_id=data["entity_a"],
                export_job_id=export_job.id,
                invoice_id=data["invoice_b"],
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()

def test_document_file_rejects_parent_from_another_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        parent = DocumentFile(
            client_id=data["client_b"],
            document_id=data["document_b"],
            file_role="original",
            storage_key="tenant-b/parent.pdf",
            file_name="parent.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="d" * 64,
            version_no=1,
        )
        db.add(parent)
        db.flush()

        child = DocumentFile(
            client_id=data["client_a"],
            document_id=data["document_a"],
            parent_file_id=parent.id,
            file_role="processed",
            storage_key="tenant-a/child.pdf",
            file_name="child.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="e" * 64,
            version_no=1,
        )
        db.add(child)

        with pytest.raises(IntegrityError):
            db.flush()


def test_document_file_accepts_parent_from_same_tenant(api, tenant_data):
    data = tenant_data

    with SessionLocal() as db:
        parent = DocumentFile(
            client_id=data["client_a"],
            document_id=data["document_a"],
            file_role="original",
            storage_key="tenant-a/parent.pdf",
            file_name="parent.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="f" * 64,
            version_no=1,
        )
        db.add(parent)
        db.flush()

        child = DocumentFile(
            client_id=data["client_a"],
            document_id=data["document_a"],
            parent_file_id=parent.id,
            file_role="processed",
            storage_key="tenant-a/child.pdf",
            file_name="child.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="g" * 64,
            version_no=1,
        )
        db.add(child)
        db.flush()

        assert child.parent_file_id == parent.id
