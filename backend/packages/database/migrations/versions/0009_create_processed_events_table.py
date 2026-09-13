"""Create the consumed-event record that makes redelivery a no-op."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_processed_events"
down_revision: str | None = "0008_organization_identities"
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
        "processed_events",
        *timestamp_columns(),
        sa.Column("consumer_group", sa.String(length=200), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=200), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint(
            "consumer_group",
            "event_id",
            name=op.f("pk_processed_events"),
        ),
        schema="trialscribe",
    )
    op.create_index(
        op.f("ix_processed_events_created_at"),
        "processed_events",
        ["created_at"],
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_processed_events_created_at"),
        table_name="processed_events",
        schema="trialscribe",
    )
    op.drop_table("processed_events", schema="trialscribe")
