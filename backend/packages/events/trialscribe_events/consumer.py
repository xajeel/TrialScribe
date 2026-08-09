"""Read events, do their work once, and never let one bad record jam the queue."""

import asyncio
import random
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.logs import event_context, get_event_logger
from trialscribe_events.publisher import EventPublisher
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.processed_events import ProcessedEventRepository
from trialscribe_events.utils.enum import DeadLetterReason
from trialscribe_events.utils.exceptions import (
    EventContractError,
    InvalidEventError,
    UnknownEventTypeError,
)

logger = get_event_logger(__name__)


class EventHandler(Protocol):
    """Do one event's work inside the transaction that also claims it."""

    async def __call__(
        self,
        envelope: EventEnvelope,
        payload: BaseModel,
        session: AsyncSession,
    ) -> None: ...


class EventConsumer:
    """Consume registered events exactly once per consumer group."""

    def __init__(
        self,
        settings: EventBusSettings,
        registry: EventRegistry,
        runtime: DatabaseRuntime,
        publisher: EventPublisher,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._runtime = runtime
        self._publisher = publisher
        self._handlers: dict[tuple[str, int], EventHandler] = {}
        self._consumer: Any = None

    def register_handler(self, event_type: str, version: int, handler: EventHandler) -> None:
        """Attach the work that one registered event type should trigger."""

        self._registry.resolve(event_type, version)
        self._handlers[(event_type, version)] = handler

    async def start(self, consumer: Any = None) -> None:
        """Subscribe to every topic this registry knows about."""

        topics = self._registry.topics(self._settings.topic_prefix)
        self._consumer = consumer or AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self._settings.bootstrap_servers,
            client_id=self._settings.client_id,
            group_id=self._settings.consumer_group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()

    async def run(self) -> None:
        """Handle records until the consumer is stopped, committing every one."""

        async for record in self._consumer:
            await self.process(record)
            await self._consumer.commit()

    async def process(self, record: Any) -> None:
        """Handle one record, absorbing every failure the queue must survive."""

        decoded = await self._decode(record)
        if decoded is None:
            return
        envelope, payload = decoded

        handler = self._handlers.get((envelope.event_type, envelope.event_version))
        if handler is None:
            logger.info(
                "event.no_handler",
                extra={"event_context": event_context(envelope, topic=record.topic)},
            )
            return

        await self._handle(record, envelope, payload, handler)

    async def _decode(self, record: Any) -> tuple[EventEnvelope, BaseModel] | None:
        """Read the record, or move it aside — retrying these can never help."""

        try:
            envelope = EventEnvelope.from_bytes(record.value)
        except InvalidEventError:
            await self._dead_letter(record, DeadLetterReason.UNDECODABLE)
            return None
        try:
            payload = self._registry.decode(envelope)
        except UnknownEventTypeError:
            await self._dead_letter(record, DeadLetterReason.UNKNOWN_EVENT_TYPE, envelope)
            return None
        except EventContractError:
            await self._dead_letter(record, DeadLetterReason.CONTRACT_MISMATCH, envelope)
            return None
        return envelope, payload

    async def _handle(
        self,
        record: Any,
        envelope: EventEnvelope,
        payload: BaseModel,
        handler: EventHandler,
    ) -> None:
        for attempt in range(1, self._settings.max_delivery_attempts + 1):
            try:
                async with self._runtime.transaction() as session:
                    repository = ProcessedEventRepository(session)
                    if not await repository.claim(self._settings.consumer_group, envelope):
                        logger.info(
                            "event.duplicate_skipped",
                            extra={
                                "event_context": event_context(envelope, topic=record.topic)
                            },
                        )
                        return
                    await handler(envelope, payload, session)
                return
            except Exception:
                logger.warning(
                    "event.handler_attempt_failed",
                    extra={
                        "event_context": event_context(
                            envelope,
                            topic=record.topic,
                            attempt=attempt,
                        )
                    },
                )
                if attempt >= self._settings.max_delivery_attempts:
                    break
                await asyncio.sleep(self._backoff_seconds(attempt))

        await self._dead_letter(record, DeadLetterReason.HANDLER_FAILED, envelope)

    def _backoff_seconds(self, attempt: int) -> float:
        """Wait a random slice of a doubling window, so retries never sync up."""

        window = min(
            self._settings.retry_backoff_cap_seconds,
            self._settings.retry_backoff_seconds * 2 ** (attempt - 1),
        )
        return random.uniform(0, window)

    async def _dead_letter(
        self,
        record: Any,
        reason: DeadLetterReason,
        envelope: EventEnvelope | None = None,
    ) -> None:
        logger.error(
            "event.moved_to_dead_letter",
            extra={
                "event_context": event_context(
                    envelope,
                    topic=record.topic,
                    partition=record.partition,
                    offset=record.offset,
                    reason=reason.value,
                )
            },
        )
        await self._publisher.publish_dead_letter(
            record.topic,
            record.value,
            reason,
            key=record.key,
        )
