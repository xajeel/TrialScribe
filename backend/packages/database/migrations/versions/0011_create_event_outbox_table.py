"""Create the outbox that keeps an event and its work in one transaction."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_event_outbox"
down_revision: str | None = "0010_jobs"
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
        "event_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("partition_key", sa.LargeBinary(), nullable=True),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_event_outbox_attempts_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_outbox")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_event_outbox_unpublished",
        "event_outbox",
        ["created_at", "id"],
        schema="trialscribe",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_outbox_unpublished",
        table_name="event_outbox",
        schema="trialscribe",
    )
    op.drop_table("event_outbox", schema="trialscribe")
