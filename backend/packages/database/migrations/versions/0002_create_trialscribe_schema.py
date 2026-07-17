"""Create the schema that owns TrialScribe application records."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_trialscribe_schema"
down_revision: str | None = "0001_enable_vector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS trialscribe")


def downgrade() -> None:
    # RESTRICT refuses to remove a schema after product tables have been added.
    op.execute("DROP SCHEMA IF EXISTS trialscribe RESTRICT")
