"""Ràng buộc trạng thái và số lần thử của processing_jobs (G4T-67)."""
from alembic import op

revision = "0003_job_state_checks"
down_revision = "0002_processing_jobs"

STATUS = "status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter')"
ATTEMPT = "attempt_no >= 1 AND attempt_no <= max_attempts"


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.create_check_constraint("ck_jobs_status", STATUS)
        batch.create_check_constraint("ck_jobs_attempt_range", ATTEMPT)


def downgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_constraint("ck_jobs_attempt_range", type_="check")
        batch.drop_constraint("ck_jobs_status", type_="check")
