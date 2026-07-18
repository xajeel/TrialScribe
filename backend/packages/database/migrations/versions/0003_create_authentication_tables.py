"""Create global accounts and revocable authentication sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_auth_tables"
down_revision: str | None = "0002_create_trialscribe_schema"
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
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("email", name=op.f("uq_accounts_email")),
        schema="trialscribe",
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_auth_sessions_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_auth_sessions_account_id"),
        "auth_sessions",
        ["account_id"],
        unique=False,
        schema="trialscribe",
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replacement_token_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["replacement_token_id"],
            ["trialscribe.refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replacement_token_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["trialscribe.auth_sessions.id"],
            name=op.f("fk_refresh_tokens_session_id_auth_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_refresh_tokens_session_id"),
        "refresh_tokens",
        ["session_id"],
        unique=False,
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_refresh_tokens_session_id"),
        table_name="refresh_tokens",
        schema="trialscribe",
    )
    op.drop_table("refresh_tokens", schema="trialscribe")
    op.drop_index(
        op.f("ix_auth_sessions_account_id"),
        table_name="auth_sessions",
        schema="trialscribe",
    )
    op.drop_table("auth_sessions", schema="trialscribe")
    op.drop_table("accounts", schema="trialscribe")
