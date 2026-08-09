"""Publish envelopes to Kafka, and move unhandleable records aside."""

from aiokafka import AIOKafkaProducer

from trialscribe_events.config import EventBusSettings
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.logs import event_context, get_event_logger
from trialscribe_events.registry import EventRegistry, dead_letter_topic
from trialscribe_events.utils.constant import (
    DEAD_LETTER_REASON_HEADER,
    PUBLISH_FAILURE_MESSAGE,
)
from trialscribe_events.utils.enum import DeadLetterReason
from trialscribe_events.utils.exceptions import EventPublishError

logger = get_event_logger(__name__)


class EventPublisher:
    """Own one idempotent producer and send envelopes to their registered topic."""

    def __init__(
        self,
        producer: AIOKafkaProducer,
        registry: EventRegistry,
        settings: EventBusSettings,
    ) -> None:
        self._producer = producer
        self._registry = registry
        self._settings = settings

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, envelope: EventEnvelope) -> None:
        """Send one envelope, keyed so its subject's events stay in order."""

        topic = self._registry.topic_of(self._settings.topic_prefix, envelope)
        try:
            await self._producer.send_and_wait(
                topic,
                value=envelope.to_bytes(),
                key=envelope.partition_key(),
                headers=envelope.headers(),
            )
        except Exception:
            raise EventPublishError(PUBLISH_FAILURE_MESSAGE) from None

    async def publish_dead_letter(
        self,
        topic: str,
        raw_value: bytes | None,
        reason: DeadLetterReason,
        key: bytes | None = None,
    ) -> None:
        """Move a record aside untouched; never raise into the consumer loop."""

        target = dead_letter_topic(topic)
        try:
            await self._producer.send_and_wait(
                target,
                value=raw_value,
                key=key,
                headers=[(DEAD_LETTER_REASON_HEADER, reason.value.encode("utf-8"))],
            )
        except Exception:
            logger.error(
                "event.dead_letter_failed",
                extra={"event_context": event_context(topic=target, reason=reason.value)},
            )
            return
        logger.warning(
            "event.dead_lettered",
            extra={"event_context": event_context(topic=target, reason=reason.value)},
        )


def create_event_publisher(
    settings: EventBusSettings,
    registry: EventRegistry,
) -> EventPublisher:
    """Build a publisher whose producer never silently loses or reorders a record."""

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.bootstrap_servers,
        client_id=settings.client_id,
        enable_idempotence=True,
        acks="all",
        request_timeout_ms=settings.request_timeout_ms(),
    )
    return EventPublisher(producer=producer, registry=registry, settings=settings)
