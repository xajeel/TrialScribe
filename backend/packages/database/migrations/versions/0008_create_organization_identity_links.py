"""Create durable tenant-scoped account identity associations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_organization_identities"
down_revision: str | None = "0007_m11_sections"
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
        "organization_identity_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["trialscribe.organizations.id"],
            name=op.f("fk_organization_identity_links_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_organization_identity_links_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_identity_links")),
        sa.UniqueConstraint(
            "organization_id",
            "account_id",
            name=op.f("uq_organization_identity_links_organization_id_account_id"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_organization_identity_links_organization_id"),
        "organization_identity_links",
        ["organization_id"],
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_organization_identity_links_account_id"),
        "organization_identity_links",
        ["account_id"],
        schema="trialscribe",
    )
    op.execute(
        """
        INSERT INTO trialscribe.organization_identity_links
            (id, organization_id, account_id, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            associations.organization_id,
            associations.account_id,
            min(associations.associated_at),
            now()
        FROM (
            SELECT organization_id, account_id, created_at AS associated_at
            FROM trialscribe.organization_memberships
            UNION ALL
            SELECT organization_id, invited_by_account_id, created_at
            FROM trialscribe.organization_invitations
            UNION ALL
            SELECT organization_id, completed_by_account_id, created_at
            FROM trialscribe.m11_sections
            WHERE completed_by_account_id IS NOT NULL
            UNION ALL
            SELECT organization_id, author_account_id, created_at
            FROM trialscribe.m11_section_revisions
            WHERE author_account_id IS NOT NULL
        ) AS associations
        GROUP BY associations.organization_id, associations.account_id
        ON CONFLICT (organization_id, account_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organization_identity_links_account_id"),
        table_name="organization_identity_links",
        schema="trialscribe",
    )
    op.drop_index(
        op.f("ix_organization_identity_links_organization_id"),
        table_name="organization_identity_links",
        schema="trialscribe",
    )
    op.drop_table("organization_identity_links", schema="trialscribe")
