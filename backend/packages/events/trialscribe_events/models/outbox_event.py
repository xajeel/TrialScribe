"""An event written down beside the work that justifies it.

A service that publishes to Kafka and writes to PostgreSQL in the same request
has two things that can each succeed alone. Publishing first can hand a consumer
a record whose row has not committed yet; committing first can leave a row whose
record was never sent. Neither ordering is safe, and a bounded retry only
narrows the window (bug B29).

Writing the record into this table inside the caller's transaction removes the
question: the event exists exactly when the work it describes exists. A relay
hands it to the broker afterwards.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_events.utils.constant import MAX_OUTBOX_TOPIC_LENGTH


class OutboxEvent(TimestampMixin, UuidPrimaryKeyMixin, Base):
    """One envelope waiting to be handed to the broker.

    Declares no foreign key: this package cannot see the tables owned by the
    services that write to it, and a key it cannot resolve breaks every statement
    the moment one is built (bug B27).
    """

    __tablename__ = "event_outbox"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_event_outbox_attempts_nonnegative"),
        Index(
            "ix_event_outbox_unpublished",
            "created_at",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    topic: Mapped[str] = mapped_column(String(MAX_OUTBOX_TOPIC_LENGTH), nullable=False)
    partition_key: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    headers: Mapped[dict[str, str]] = mapped_column(
        JSONB(),
        nullable=False,
        default=dict,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger(), nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
