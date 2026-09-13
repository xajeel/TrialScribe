"""Create the table that records one section generation attempt and its prompt."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_section_generation_attempts"
down_revision: str | None = "0013_evidence_chunks"
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
        "section_generation_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("section_number", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column(
            "citation_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.CheckConstraint(
            "attempt >= 1",
            name=op.f("ck_section_generation_attempts_attempt"),
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'skipped')",
            name=op.f("ck_section_generation_attempts_status"),
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN ("
            "'missing_section', 'empty_output', 'provider_failed', 'revision_conflict')",
            name=op.f("ck_section_generation_attempts_error_code"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_section_generation_attempts_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["trialscribe.jobs.id"],
            name=op.f("fk_section_generation_attempts_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section_generation_attempts")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_section_generation_attempts_scope",
        "section_generation_attempts",
        ["organization_id", "conversation_id", "job_id", "section_number"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_section_generation_attempts_scope",
        table_name="section_generation_attempts",
        schema="trialscribe",
    )
    op.drop_table("section_generation_attempts", schema="trialscribe")
