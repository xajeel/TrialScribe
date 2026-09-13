"""Create organizations, memberships, and single-use invitations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_organization_rbac"
down_revision: str | None = "0003_auth_tables"
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
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.CheckConstraint(
            "name = btrim(name) AND char_length(name) BETWEEN 1 AND 120",
            name=op.f("ck_organizations_name_length"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        schema="trialscribe",
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member')",
            name=op.f("ck_organization_memberships_role"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["trialscribe.organizations.id"],
            name=op.f("fk_organization_memberships_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_organization_memberships_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_memberships")),
        sa.UniqueConstraint(
            "organization_id",
            "account_id",
            name=op.f("uq_organization_memberships_organization_id_account_id"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_organization_memberships_organization_id"),
        "organization_memberships",
        ["organization_id"],
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_organization_memberships_account_id"),
        "organization_memberships",
        ["account_id"],
        schema="trialscribe",
    )
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("invited_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('admin', 'member')",
            name=op.f("ck_organization_invitations_role"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["trialscribe.organizations.id"],
            name=op.f("fk_organization_invitations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_organization_invitations_invited_by_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_invitations")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_organization_invitations_token_hash"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_organization_invitations_organization_id"),
        "organization_invitations",
        ["organization_id"],
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_organization_invitations_invited_by_account_id"),
        "organization_invitations",
        ["invited_by_account_id"],
        schema="trialscribe",
    )
    op.create_index(
        "uq_organization_invitations_pending_email",
        "organization_invitations",
        ["organization_id", "email"],
        unique=True,
        schema="trialscribe",
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_organization_invitations_pending_email",
        table_name="organization_invitations",
        schema="trialscribe",
    )
    op.drop_index(
        op.f("ix_organization_invitations_invited_by_account_id"),
        table_name="organization_invitations",
        schema="trialscribe",
    )
    op.drop_index(
        op.f("ix_organization_invitations_organization_id"),
        table_name="organization_invitations",
        schema="trialscribe",
    )
    op.drop_table("organization_invitations", schema="trialscribe")
    op.drop_index(
        op.f("ix_organization_memberships_account_id"),
        table_name="organization_memberships",
        schema="trialscribe",
    )
    op.drop_index(
        op.f("ix_organization_memberships_organization_id"),
        table_name="organization_memberships",
        schema="trialscribe",
    )
    op.drop_table("organization_memberships", schema="trialscribe")
    op.drop_table("organizations", schema="trialscribe")
