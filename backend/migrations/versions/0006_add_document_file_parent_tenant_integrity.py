
"""Add tenant integrity to document file parent references.

Revision ID: 51a177406313
Revises: 01b3a304aabc
"""

from alembic import op


revision = "51a177406313"
down_revision = "01b3a304aabc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_document_files_id_client",
        "document_files",
        ["id", "client_id"],
    )

    op.drop_constraint(
        "document_files_parent_file_id_fkey",
        "document_files",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_document_files_parent_client",
        "document_files",
        "document_files",
        ["parent_file_id", "client_id"],
        ["id", "client_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_files_parent_client",
        "document_files",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "document_files_parent_file_id_fkey",
        "document_files",
        "document_files",
        ["parent_file_id"],
        ["id"],
    )

    op.drop_constraint(
        "uq_document_files_id_client",
        "document_files",
        type_="unique",
    )
