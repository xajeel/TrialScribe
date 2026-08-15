"""Create the table that stores one protocol readiness snapshot per check."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_protocol_readiness_checks"
down_revision: str | None = "0015_m11_revision_actions"
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
        "protocol_readiness_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("protocol_title", sa.Text(), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "issues",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_protocol_readiness_checks_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["trialscribe.jobs.id"],
            name=op.f("fk_protocol_readiness_checks_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_protocol_readiness_checks")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_protocol_readiness_checks_scope",
        "protocol_readiness_checks",
        ["organization_id", "conversation_id", "computed_at"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_protocol_readiness_checks_scope",
        table_name="protocol_readiness_checks",
        schema="trialscribe",
    )
    op.drop_table("protocol_readiness_checks", schema="trialscribe")
