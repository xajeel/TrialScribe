"""Enable pgvector as a managed database capability."""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_enable_vector"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Removing this extension could destroy vector columns owned by later features.
    pass
