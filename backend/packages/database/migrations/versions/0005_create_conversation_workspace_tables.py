"""Create durable, tenant-scoped conversation workspaces."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_conversation_workspaces"
down_revision: str | None = "0004_organization_rbac"
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
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_account_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 120",
            name=op.f("ck_conversations_title_length"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["trialscribe.organizations.id"],
            name=op.f("fk_conversations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_conversations_owner_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            name=op.f("uq_conversations_id_organization_id"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        "ix_conversations_organization_archive_activity",
        "conversations",
        ["organization_id", "archived_at", "last_activity_at", "id"],
        schema="trialscribe",
    )

    op.create_table(
        "conversation_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_conversation_access_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_id"],
            [
                "trialscribe.organization_memberships.organization_id",
                "trialscribe.organization_memberships.account_id",
            ],
            name=op.f("fk_conversation_access_organization_membership"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_access")),
        sa.UniqueConstraint(
            "conversation_id",
            "account_id",
            name=op.f("uq_conversation_access_conversation_id_account_id"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        "ix_conversation_access_organization_account",
        "conversation_access",
        ["organization_id", "account_id", "conversation_id"],
        schema="trialscribe",
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("author_account_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name=op.f("ck_conversation_messages_role"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(content)) >= 1 AND char_length(content) <= 20000",
            name=op.f("ck_conversation_messages_content_length"),
        ),
        sa.CheckConstraint(
            "sequence > 0",
            name=op.f("ck_conversation_messages_sequence_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_conversation_messages_conversation_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_conversation_messages_author_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_messages")),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name=op.f("uq_conversation_messages_conversation_id_sequence"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        "ix_conversation_messages_organization_conversation_sequence",
        "conversation_messages",
        ["organization_id", "conversation_id", "sequence"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_messages_organization_conversation_sequence",
        table_name="conversation_messages",
        schema="trialscribe",
    )
    op.drop_table("conversation_messages", schema="trialscribe")
    op.drop_index(
        "ix_conversation_access_organization_account",
        table_name="conversation_access",
        schema="trialscribe",
    )
    op.drop_table("conversation_access", schema="trialscribe")
    op.drop_index(
        "ix_conversations_organization_archive_activity",
        table_name="conversations",
        schema="trialscribe",
    )
    op.drop_table("conversations", schema="trialscribe")
