from alembic import op
import sqlalchemy as sa


revision = 'd83358b75ff4'
down_revision = "51a177406313"
branch_labels = None
depends_on = None


FIELD_STATUSES = (
    "present",
    "missing",
    "not_present",
    "needs_review",
    "conflict",
)

EXTRACTION_METHODS = (
    "xml",
    "pdf_text",
    "ocr",
    "manual",
)


def upgrade() -> None:
    op.add_column(
        "extracted_fields",
        sa.Column("field_status", sa.String(24), nullable=True),
    )
    op.add_column(
        "extracted_fields",
        sa.Column("extraction_method", sa.String(24), nullable=True),
    )

    # Không tự gán dữ liệu giả cho các bản ghi cũ.
    connection = op.get_bind()
    existing_rows = connection.execute(
        sa.text("SELECT COUNT(*) FROM extracted_fields")
    ).scalar_one()

    if existing_rows:
        raise RuntimeError(
            f"extracted_fields contains {existing_rows} existing rows. "
            "Define a valid backfill mapping before applying this migration."
        )

    with op.batch_alter_table("extracted_fields") as batch:
        batch.alter_column(
            "field_status",
            existing_type=sa.String(24),
            nullable=False,
        )
        batch.alter_column(
            "extraction_method",
            existing_type=sa.String(24),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_extracted_fields_field_status",
            "field_status IN "
            "('present', 'missing', 'not_present', 'needs_review', 'conflict')",
        )
        batch.create_check_constraint(
            "ck_extracted_fields_extraction_method",
            "extraction_method IN ('xml', 'pdf_text', 'ocr', 'manual')",
        )


def downgrade() -> None:
    with op.batch_alter_table("extracted_fields") as batch:
        batch.drop_constraint(
            "ck_extracted_fields_extraction_method",
            type_="check",
        )
        batch.drop_constraint(
            "ck_extracted_fields_field_status",
            type_="check",
        )
        batch.drop_column("extraction_method")
        batch.drop_column("field_status")

