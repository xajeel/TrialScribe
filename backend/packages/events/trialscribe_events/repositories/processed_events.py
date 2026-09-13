"""Claim an event once, so a redelivery cannot repeat its effect."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.models.processed_event import ProcessedEvent


class ProcessedEventRepository:
    """Record which events a consumer group has already handled."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, consumer_group: str, envelope: EventEnvelope) -> bool:
        """Return True the first time this group sees an event, False afterwards.

        The insert runs in the caller's transaction, so it is only durable if the
        handler's work commits with it. `RETURNING` reports the outcome directly:
        one row when this call inserted it, no rows when it was already there.
        Row counts cannot be used here — an ORM-entity insert reports -1.
        """

        statement = (
            insert(ProcessedEvent.__table__)
            .values(
                consumer_group=consumer_group,
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                organization_id=envelope.organization_id,
            )
            .on_conflict_do_nothing(index_elements=["consumer_group", "event_id"])
            .returning(ProcessedEvent.__table__.c.event_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None
