"""Hand stored events to the broker, after the work they describe is durable."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from trialscribe_db.runtime import DatabaseRuntime
from trialscribe_events.logs import event_context, get_event_logger
from trialscribe_events.models.outbox_event import OutboxEvent
from trialscribe_events.publisher import EventPublisher
from trialscribe_events.repositories.outbox import OutboxRepository

logger = get_event_logger(__name__)


@dataclass(frozen=True, slots=True)
class RelayResult:
    """What one pass over the outbox achieved."""

    published: int
    failed: int

    def __bool__(self) -> bool:
        return bool(self.published or self.failed)


class OutboxRelay:
    """Deliver stored events, and never lose one it failed to deliver.

    A batch is claimed, published, and settled inside a single transaction, so an
    event is marked delivered only if it really reached the broker. Anything that
    did not stays pending and is picked up by the next pass — an event may be
    delivered more than once, never fewer than once, which is the same guarantee
    consumers already handle through the processed-event inbox.
    """

    def __init__(
        self,
        runtime: DatabaseRuntime,
        publisher: EventPublisher,
        batch_size: int,
        poll_seconds: float,
    ) -> None:
        self._runtime = runtime
        self._publisher = publisher
        self._batch_size = batch_size
        self._poll_seconds = poll_seconds

    async def drain_once(self) -> RelayResult:
        """Deliver one batch, reporting what reached the broker and what did not."""

        async with self._runtime.transaction() as session:
            repository = OutboxRepository(session)
            pending = await repository.claim_unpublished(self._batch_size)
            if not pending:
                return RelayResult(published=0, failed=0)

            delivered: list[OutboxEvent] = []
            undelivered: list[OutboxEvent] = []
            for record in pending:
                if await self._deliver(record):
                    delivered.append(record)
                else:
                    undelivered.append(record)

            now = datetime.now(UTC)
            await repository.mark_published([record.id for record in delivered], now)
            await repository.record_failure([record.id for record in undelivered], now)
            return RelayResult(published=len(delivered), failed=len(undelivered))

    async def run(self, stop: asyncio.Event) -> None:
        """Drain continuously until asked to stop, pausing when there is nothing to do."""

        while not stop.is_set():
            try:
                result = await self.drain_once()
            except Exception:
                logger.error(
                    "event.outbox_drain_failed",
                    extra={"event_context": event_context(reason="drain_failed")},
                )
                result = RelayResult(published=0, failed=0)
            if result.published:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass

    async def _deliver(self, record: OutboxEvent) -> bool:
        try:
            await self._publisher.publish_raw(
                record.topic,
                record.payload,
                key=record.partition_key,
                headers=[
                    (name, value.encode("utf-8"))
                    for name, value in (record.headers or {}).items()
                ],
            )
        except Exception:
            logger.warning(
                "event.outbox_delivery_failed",
                extra={"event_context": event_context(topic=record.topic)},
            )
            return False
        return True
