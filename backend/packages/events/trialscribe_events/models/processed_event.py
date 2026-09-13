"""The record that makes a redelivered event a no-op."""

from uuid import UUID

from sqlalchemy import Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin
from trialscribe_events.utils.constant import (
    MAX_CONSUMER_GROUP_LENGTH,
    MAX_EVENT_TYPE_LENGTH,
)


class ProcessedEvent(TimestampMixin, Base):
    """Mark one event as already handled by one consumer group.

    The row is written inside the same transaction as the handler's work, so
    the effect and the record of it commit or roll back together.
    """

    __tablename__ = "processed_events"
    __table_args__ = (Index("ix_processed_events_created_at", "created_at"),)

    consumer_group: Mapped[str] = mapped_column(
        String(MAX_CONSUMER_GROUP_LENGTH),
        primary_key=True,
    )
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(MAX_EVENT_TYPE_LENGTH), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
