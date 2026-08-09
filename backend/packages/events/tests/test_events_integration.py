import asyncio
import os
import uuid
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import DatabaseRuntime, create_database_runtime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.consumer import EventConsumer
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.publisher import EventPublisher, create_event_publisher
from trialscribe_events.registry import EventRegistry, dead_letter_topic
from trialscribe_events.topics import ensure_topics

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_EVENTS_INTEGRATION") != "1",
        reason="requires the isolated Kafka and PostgreSQL test project",
    ),
]

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000091")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000092")
EVENT_TYPE = "probe.work.requested"
CONSUME_TIMEOUT_SECONDS = 30.0
DEAD_LETTER_TIMEOUT_SECONDS = 30.0


class WorkRequested(BaseModel):
    work_id: str


def run_identifier() -> str:
    return uuid.uuid4().hex[:12]


def event_settings(identifier: str, **overrides: Any) -> EventBusSettings:
    values: dict[str, Any] = {
        "bootstrap_servers": os.environ["EVENTS_BOOTSTRAP_SERVERS"],
        "topic_prefix": f"trialscribe-it-{identifier}",
        "client_id": f"events-it-{identifier}",
        "consumer_group": f"events-it-{identifier}",
        "topic_partitions": 1,
        "topic_replication_factor": 1,
        "retry_backoff_seconds": 0.05,
        "retry_backoff_cap_seconds": 0.2,
    }
    values.update(overrides)
    return EventBusSettings(**values)


def probe_registry() -> EventRegistry:
    registry = EventRegistry()
    registry.register(EVENT_TYPE, 1, "probe", WorkRequested)
    return registry


def build_envelope(registry: EventRegistry, work_id: str) -> EventEnvelope:
    return registry.build(
        event_type=EVENT_TYPE,
        version=1,
        organization_id=ORGANIZATION_ID,
        subject=work_id,
        correlation_id=CORRELATION_ID,
        producer="events-integration-test",
        payload=WorkRequested(work_id=work_id),
    )


async def drain(consumer: EventConsumer, expected: int, timeout: float) -> int:
    """Process records until `expected` have been seen or the timeout expires."""

    processed = 0
    deadline = asyncio.get_running_loop().time() + timeout
    while processed < expected and asyncio.get_running_loop().time() < deadline:
        batches = await consumer._consumer.getmany(timeout_ms=500)
        for records in batches.values():
            for record in records:
                await consumer.process(record)
                await consumer._consumer.commit()
                processed += 1
    return processed


async def read_dead_letters(
    settings: EventBusSettings,
    topic: str,
    timeout: float,
) -> list[bytes]:
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        dead_letter_topic(topic),
        bootstrap_servers=settings.bootstrap_servers,
        group_id=f"{settings.consumer_group}-dlq-reader",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        values: list[bytes] = []
        deadline = asyncio.get_running_loop().time() + timeout
        while not values and asyncio.get_running_loop().time() < deadline:
            batches = await consumer.getmany(timeout_ms=500)
            for records in batches.values():
                values.extend(record.value for record in records)
        return values
    finally:
        await consumer.stop()


async def processed_event_count(runtime: DatabaseRuntime, event_id: UUID) -> int:
    async with runtime.transaction() as session:
        count = await session.scalar(
            text(
                "SELECT count(*) FROM trialscribe.processed_events "
                "WHERE event_id = :event_id"
            ),
            {"event_id": event_id},
        )
    return int(count or 0)


async def open_backbone(
    identifier: str,
    **setting_overrides: Any,
) -> tuple[EventBusSettings, EventRegistry, DatabaseRuntime, EventPublisher, EventConsumer]:
    settings = event_settings(identifier, **setting_overrides)
    registry = probe_registry()
    runtime = create_database_runtime(DatabaseSettings())
    publisher = create_event_publisher(settings, registry)
    await ensure_topics(settings, registry.topics(settings.topic_prefix))
    await publisher.start()
    consumer = EventConsumer(settings, registry, runtime, publisher)
    return settings, registry, runtime, publisher, consumer


async def close_backbone(
    runtime: DatabaseRuntime,
    publisher: EventPublisher,
    consumer: EventConsumer,
) -> None:
    await consumer.stop()
    await publisher.stop()
    await runtime.dispose()


async def one_event_runs_its_work_once() -> tuple[int, int]:
    identifier = run_identifier()
    settings, registry, runtime, publisher, consumer = await open_backbone(identifier)
    handled: list[str] = []

    async def handler(
        envelope: EventEnvelope,
        payload: BaseModel,
        session: AsyncSession,
    ) -> None:
        handled.append(envelope.subject)

    consumer.register_handler(EVENT_TYPE, 1, handler)
    await consumer.start()
    try:
        envelope = build_envelope(registry, f"work-{identifier}")
        await publisher.publish(envelope)
        await drain(consumer, 1, CONSUME_TIMEOUT_SECONDS)
        rows = await processed_event_count(runtime, envelope.event_id)
        return len(handled), rows
    finally:
        await close_backbone(runtime, publisher, consumer)


async def a_redelivered_event_runs_its_work_once() -> tuple[int, int]:
    identifier = run_identifier()
    settings, registry, runtime, publisher, consumer = await open_backbone(identifier)
    handled: list[str] = []

    async def handler(
        envelope: EventEnvelope,
        payload: BaseModel,
        session: AsyncSession,
    ) -> None:
        handled.append(envelope.subject)

    consumer.register_handler(EVENT_TYPE, 1, handler)
    await consumer.start()
    try:
        envelope = build_envelope(registry, f"work-{identifier}")
        await publisher.publish(envelope)
        await publisher.publish(envelope)
        await drain(consumer, 2, CONSUME_TIMEOUT_SECONDS)
        rows = await processed_event_count(runtime, envelope.event_id)
        return len(handled), rows
    finally:
        await close_backbone(runtime, publisher, consumer)


async def a_failing_event_is_moved_aside_and_the_reader_carries_on() -> tuple[int, int, int]:
    identifier = run_identifier()
    settings, registry, runtime, publisher, consumer = await open_backbone(
        identifier,
        max_delivery_attempts=3,
    )
    attempts: list[str] = []
    succeeded: list[str] = []
    poison_id = f"poison-{identifier}"

    async def handler(
        envelope: EventEnvelope,
        payload: BaseModel,
        session: AsyncSession,
    ) -> None:
        if envelope.subject == poison_id:
            attempts.append(envelope.subject)
            raise RuntimeError("integration probe failure")
        succeeded.append(envelope.subject)

    consumer.register_handler(EVENT_TYPE, 1, handler)
    await consumer.start()
    try:
        topic = f"{consumer._settings.topic_prefix}.probe.v1"
        await publisher.publish(build_envelope(registry, poison_id))
        await publisher.publish(build_envelope(registry, f"good-{identifier}"))
        await drain(consumer, 2, CONSUME_TIMEOUT_SECONDS)
        dead_letters = await read_dead_letters(
            consumer._settings,
            topic,
            DEAD_LETTER_TIMEOUT_SECONDS,
        )
        return len(attempts), len(succeeded), len(dead_letters)
    finally:
        await close_backbone(runtime, publisher, consumer)


def test_a_published_event_is_consumed_and_its_work_runs_once() -> None:
    handled, rows = asyncio.run(one_event_runs_its_work_once())

    assert handled == 1
    assert rows == 1


def test_the_same_event_delivered_twice_runs_its_work_once() -> None:
    handled, rows = asyncio.run(a_redelivered_event_runs_its_work_once())

    assert handled == 1
    assert rows == 1


def test_a_failing_event_is_dead_lettered_and_the_next_one_still_runs() -> None:
    attempts, succeeded, dead_letters = asyncio.run(
        a_failing_event_is_moved_aside_and_the_reader_carries_on()
    )

    assert attempts == 3
    assert succeeded == 1
    assert dead_letters == 1
