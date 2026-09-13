"""Create durable ICH M11 section workspaces and revision history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_m11_sections"
down_revision: str | None = "0006_document_sources"
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
        "m11_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("section_number", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column(
            "current_revision",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_account_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'done')",
            name=op.f("ck_m11_sections_status"),
        ),
        sa.CheckConstraint(
            "current_revision >= 0",
            name=op.f("ck_m11_sections_current_revision_nonnegative"),
        ),
        sa.CheckConstraint(
            "section_number = btrim(section_number) "
            "AND char_length(section_number) BETWEEN 1 AND 8",
            name=op.f("ck_m11_sections_number_length"),
        ),
        sa.CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 200",
            name=op.f("ck_m11_sections_title_length"),
        ),
        sa.CheckConstraint(
            "char_length(instructions) <= 20000",
            name=op.f("ck_m11_sections_instructions_length"),
        ),
        sa.CheckConstraint(
            "char_length(content) <= 200000",
            name=op.f("ck_m11_sections_content_length"),
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND completed_at IS NULL "
            "AND completed_by_account_id IS NULL) "
            "OR (status = 'done' AND completed_at IS NOT NULL)",
            name=op.f("ck_m11_sections_completion_state"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_m11_sections_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_m11_sections_completed_by_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_m11_sections")),
        sa.UniqueConstraint(
            "id",
            "conversation_id",
            "organization_id",
            name=op.f("uq_m11_sections_id_conversation_organization"),
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "organization_id",
            "section_number",
            name=op.f("uq_m11_sections_conversation_number"),
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "organization_id",
            "position",
            name=op.f("uq_m11_sections_conversation_position"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        "ix_m11_sections_organization_conversation_position",
        "m11_sections",
        ["organization_id", "conversation_id", "position"],
        schema="trialscribe",
    )

    op.create_table(
        "m11_section_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("author_account_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "revision_number > 0",
            name=op.f("ck_m11_section_revisions_number_positive"),
        ),
        sa.CheckConstraint(
            "action IN ('revised', 'done', 'reopened')",
            name=op.f("ck_m11_section_revisions_action"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'done')",
            name=op.f("ck_m11_section_revisions_status"),
        ),
        sa.CheckConstraint(
            "(action = 'done' AND status = 'done') "
            "OR (action IN ('revised', 'reopened') AND status = 'draft')",
            name=op.f("ck_m11_section_revisions_action_status"),
        ),
        sa.CheckConstraint(
            "char_length(instructions) <= 20000",
            name=op.f("ck_m11_section_revisions_instructions_length"),
        ),
        sa.CheckConstraint(
            "char_length(content) <= 200000",
            name=op.f("ck_m11_section_revisions_content_length"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "conversation_id", "organization_id"],
            [
                "trialscribe.m11_sections.id",
                "trialscribe.m11_sections.conversation_id",
                "trialscribe.m11_sections.organization_id",
            ],
            name=op.f("fk_m11_section_revisions_section_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_m11_section_revisions_author_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_m11_section_revisions")),
        sa.UniqueConstraint(
            "section_id",
            "revision_number",
            name=op.f("uq_m11_section_revisions_section_revision"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        "ix_m11_section_revisions_scope_revision",
        "m11_section_revisions",
        [
            "organization_id",
            "conversation_id",
            "section_id",
            "revision_number",
        ],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_m11_section_revisions_scope_revision",
        table_name="m11_section_revisions",
        schema="trialscribe",
    )
    op.drop_table("m11_section_revisions", schema="trialscribe")
    op.drop_index(
        "ix_m11_sections_organization_conversation_position",
        table_name="m11_sections",
        schema="trialscribe",
    )
    op.drop_table("m11_sections", schema="trialscribe")
