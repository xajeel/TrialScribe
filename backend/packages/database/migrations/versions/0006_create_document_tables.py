"""Create durable, tenant-scoped conversation documents."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_document_sources"
down_revision: str | None = "0005_conversation_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> tuple[sa.Column[object], sa.Column[object]]:
    """Return the shared UTC timestamp columns for an application table."""

    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_account_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('trial_data', 'research_document')",
            name=op.f("ck_documents_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name=op.f("ck_documents_status"),
        ),
        sa.CheckConstraint(
            "byte_size > 0",
            name=op.f("ck_documents_byte_size_positive"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(filename)) >= 1 AND char_length(filename) <= 255",
            name=op.f("ck_documents_filename_length"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_documents_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_documents_uploaded_by_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_documents_organization_conversation_created",
        "documents",
        ["organization_id", "conversation_id", "created_at", "id"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_organization_conversation_created",
        table_name="documents",
        schema="trialscribe",
    )
    op.drop_table("documents", schema="trialscribe")
