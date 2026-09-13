"""Create the table that records every provider attempt and its integer-micro cost."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_provider_calls"
down_revision: str | None = "0011_event_outbox"
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
        "provider_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("pricing_version", sa.String(length=32), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "operation IN ('chat', 'embed')",
            name=op.f("ck_provider_calls_operation"),
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'timeout', 'rate_limited', 'circuit_open', 'error')",
            name=op.f("ck_provider_calls_outcome"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name=op.f("ck_provider_calls_input_tokens"),
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name=op.f("ck_provider_calls_output_tokens"),
        ),
        sa.CheckConstraint(
            "cache_hit_tokens >= 0",
            name=op.f("ck_provider_calls_cache_hit_tokens"),
        ),
        sa.CheckConstraint(
            "cost_micros >= 0",
            name=op.f("ck_provider_calls_cost_micros"),
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name=op.f("ck_provider_calls_latency_ms"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["trialscribe.organizations.id"],
            name=op.f("fk_provider_calls_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name=op.f("fk_provider_calls_conversation_organization"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["trialscribe.jobs.id"],
            name=op.f("fk_provider_calls_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trialscribe.accounts.id"],
            name=op.f("fk_provider_calls_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_calls")),
        schema="trialscribe",
    )
    op.create_index(
        "ix_provider_calls_organization_job_created",
        "provider_calls",
        ["organization_id", "job_id", "created_at", "id"],
        schema="trialscribe",
    )
    op.create_index(
        "uq_provider_calls_succeeded_idempotency",
        "provider_calls",
        ["idempotency_key"],
        unique=True,
        schema="trialscribe",
        postgresql_where=sa.text("outcome = 'succeeded'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_provider_calls_succeeded_idempotency",
        table_name="provider_calls",
        schema="trialscribe",
        postgresql_where=sa.text("outcome = 'succeeded'"),
    )
    op.drop_index(
        "ix_provider_calls_organization_job_created",
        table_name="provider_calls",
        schema="trialscribe",
    )
    op.drop_table("provider_calls", schema="trialscribe")
