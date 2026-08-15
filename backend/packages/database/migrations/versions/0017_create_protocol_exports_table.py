"""Create the table that stores one assembled protocol Word file per export job."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_protocol_exports"
down_revision: str | None = "0016_protocol_readiness_checks"
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
        "protocol_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('done-only', 'include-drafts')",
            name=op.f("ck_protocol_exports_scope"),
        ),
        sa.CheckConstraint(
            "byte_size > 0",
            name=op.f("ck_protocol_exports_byte_size"),
        ),
        sa.CheckConstraint(
            "section_count >= 1",
            name=op.f("ck_protocol_exports_section_count"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(filename)) >= 1 AND char_length(filename) <= 255",
            name=op.f("ck_protocol_exports_filename"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_protocol_exports_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["trialscribe.jobs.id"],
            name=op.f("fk_protocol_exports_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_protocol_exports_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_protocol_exports")),
        sa.UniqueConstraint("job_id", name=op.f("uq_protocol_exports_job_id")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_protocol_exports_scope",
        "protocol_exports",
        ["organization_id", "conversation_id", "created_at"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_protocol_exports_scope",
        table_name="protocol_exports",
        schema="trialscribe",
    )
    op.drop_table("protocol_exports", schema="trialscribe")
