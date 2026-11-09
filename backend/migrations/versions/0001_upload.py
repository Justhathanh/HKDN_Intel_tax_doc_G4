"""Bảng tiếp nhận tài liệu (G4T-10, G4T-11)."""
import sqlalchemy as sa
from alembic import op

revision = "0001_upload"
down_revision = None


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table("clients", _id(), sa.Column("name", sa.String(255), nullable=False),
                    sa.Column("tax_id", sa.String(20), nullable=False))
    op.create_table("batches", _id(), sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
                    sa.Column("engagement_id", sa.String(64), nullable=False),
                    sa.Column("created_by", sa.String(128), nullable=False), _ts("created_at"))
    op.create_index("ix_batches_client_id", "batches", ["client_id"])
    op.create_table(
        "documents", _id(),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("uploaded_by", sa.String(128), nullable=False), _ts("received_at"),
        sa.UniqueConstraint("client_id", "sha256", name="uq_documents_client_sha256"))
    op.create_index("ix_documents_client_id", "documents", ["client_id"])
    op.create_index("ix_documents_batch_id", "documents", ["batch_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_table(
        "submissions", _id(),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True), _ts("received_at"),
        sa.UniqueConstraint("client_id", "idempotency_key", name="uq_submissions_client_key"))
    op.create_index("ix_submissions_client_id", "submissions", ["client_id"])
    op.create_index("ix_submissions_batch_id", "submissions", ["batch_id"])
    op.create_index("ix_submissions_document_id", "submissions", ["document_id"])
    op.create_table(
        "state_events", _id(),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("from_state", sa.String(32), nullable=True),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), _ts("at"))
    op.create_index("ix_state_events_document_id", "state_events", ["document_id"])


def downgrade() -> None:
    for table in ("state_events", "submissions", "documents", "batches", "clients"):
        op.drop_table(table)
