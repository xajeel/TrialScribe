"""Store events beside their work, and hand them out one batch at a time."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.models.outbox_event import OutboxEvent


class OutboxRepository:
    """Write pending events, and claim them for delivery without collisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, topic: str, envelope: EventEnvelope) -> OutboxEvent:
        """Record an envelope in the caller's transaction, exactly as it will be sent.

        The bytes stored here are the bytes the broker receives, so delivery never
        re-serializes and can never drift from what the writer intended.
        """

        record = OutboxEvent(
            topic=topic,
            partition_key=envelope.partition_key(),
            payload=envelope.to_bytes(),
            headers={name: value.decode("utf-8") for name, value in envelope.headers()},
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def claim_unpublished(self, limit: int) -> list[OutboxEvent]:
        """Take the oldest undelivered events, skipping any another relay holds.

        `FOR UPDATE SKIP LOCKED` is what lets several worker processes drain the
        same table at once without two of them sending the same record.
        """

        statement = (
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def mark_published(self, ids: list[UUID], now: datetime) -> list[UUID]:
        """Record which events really reached the broker.

        Reads the outcome from the rows it returns; an ORM-entity write reports a
        row count of -1 and can never be trusted for this (bug B23).
        """

        if not ids:
            return []
        statement = (
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(ids), OutboxEvent.published_at.is_(None))
            .values(published_at=now, updated_at=now)
            .returning(OutboxEvent.id)
            .execution_options(synchronize_session=False)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def record_failure(self, ids: list[UUID], now: datetime) -> list[UUID]:
        """Count a failed delivery, leaving the event pending for the next pass."""

        if not ids:
            return []
        statement = (
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(ids), OutboxEvent.published_at.is_(None))
            .values(attempts=OutboxEvent.attempts + 1, updated_at=now)
            .returning(OutboxEvent.id)
            .execution_options(synchronize_session=False)
        )
        return list((await self._session.execute(statement)).scalars().all())
