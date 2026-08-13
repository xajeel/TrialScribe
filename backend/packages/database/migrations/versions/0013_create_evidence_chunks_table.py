"""Create the table that holds evidence text and provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_evidence_chunks"
down_revision: str | None = "0012_provider_calls"
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
        "evidence_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_identity", sa.String(length=500), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('trial_data', 'research_document', 'web', 'probe')",
            name=op.f("ck_evidence_chunks_source_kind"),
        ),
        sa.CheckConstraint(
            "end_char >= start_char",
            name=op.f("ck_evidence_chunks_char_span"),
        ),
        sa.CheckConstraint(
            "char_length(text) >= 1",
            name=op.f("ck_evidence_chunks_text_length"),
        ),
        sa.CheckConstraint(
            "embedding_dimensions > 0",
            name=op.f("ck_evidence_chunks_embedding_dimensions"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_evidence_chunks_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_chunks")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_evidence_chunks_organization_conversation_id",
        "evidence_chunks",
        ["organization_id", "conversation_id", "id"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_chunks_organization_conversation_id",
        table_name="evidence_chunks",
        schema="trialscribe",
    )
    op.drop_table("evidence_chunks", schema="trialscribe")
