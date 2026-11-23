"""Bảng processing_jobs cho xử lý nền (G4T-66)."""
import sqlalchemy as sa
from alembic import op

revision = "0002_processing_jobs"
down_revision = "0001_upload"

ACTIVE = sa.text("status IN ('queued', 'running')")


def _ts(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_of_job_id", sa.String(36), sa.ForeignKey("processing_jobs.id"), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("processor_version", sa.String(64), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        _ts("lease_expires_at"), _ts("created_at", False), _ts("next_attempt_at", False),
        _ts("started_at"), _ts("finished_at"), _ts("updated_at", False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(300), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("document_id", "job_type", "attempt_no", name="uq_jobs_document_type_attempt"),
    )
    op.create_index("ix_processing_jobs_client_id", "processing_jobs", ["client_id"])
    op.create_index("ix_processing_jobs_document_id", "processing_jobs", ["document_id"])
    op.create_index("ix_processing_jobs_correlation_id", "processing_jobs", ["correlation_id"])
    op.create_index("ix_jobs_status_next_attempt", "processing_jobs", ["status", "next_attempt_at"])
    op.create_index("uq_jobs_one_active", "processing_jobs", ["document_id", "job_type"], unique=True,
                    postgresql_where=ACTIVE, sqlite_where=ACTIVE)


def downgrade() -> None:
    op.drop_table("processing_jobs")
