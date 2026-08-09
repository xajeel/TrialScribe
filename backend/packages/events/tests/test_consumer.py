import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel

from trialscribe_events.config import EventBusSettings
from trialscribe_events.consumer import EventConsumer
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.enum import DeadLetterReason
from trialscribe_events.utils.exceptions import UnknownEventTypeError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000003")
OCCURRED_AT = datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC)
TOPIC = "trialscribe.job.v1"
CLAIMED = UUID("00000000-0000-4000-8000-000000000004")


class JobRequested(BaseModel):
    job_id: str


class FakeRecord:
    def __init__(self, value: bytes | None, key: bytes | None = b"job-1") -> None:
        self.topic = TOPIC
        self.partition = 0
        self.offset = 17
        self.value = value
        self.key = key


class FakeResult:
    """One returned row means this call claimed the event; none means it was already claimed."""

    def __init__(self, returned: UUID | None) -> None:
        self._returned = returned

    def scalar_one_or_none(self) -> UUID | None:
        return self._returned


class FakeSession:
    def __init__(self, claims: list[UUID | None]) -> None:
        self._claims = claims
        self.executed = 0

    async def execute(self, _statement: Any) -> FakeResult:
        index = min(self.executed, len(self._claims) - 1)
        self.executed += 1
        return FakeResult(self._claims[index])

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeRuntime:
    def __init__(self, claims: list[UUID | None] | None = None) -> None:
        self.session = FakeSession(claims if claims is not None else [CLAIMED])
        self.transactions = 0
        self.rolled_back = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeSession]:
        self.transactions += 1
        try:
            yield self.session
        except BaseException:
            self.rolled_back += 1
            raise


class FakePublisher:
    def __init__(self) -> None:
        self.dead_letters: list[tuple[str, bytes | None, DeadLetterReason]] = []

    async def publish_dead_letter(
        self,
        topic: str,
        raw_value: bytes | None,
        reason: DeadLetterReason,
        key: bytes | None = None,
    ) -> None:
        self.dead_letters.append((topic, raw_value, reason))


class FakeKafkaConsumer:
    def __init__(self, records: list[FakeRecord]) -> None:
        self.records = records
        self.commits = 0
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def commit(self) -> None:
        self.commits += 1

    def __aiter__(self) -> "FakeKafkaConsumer":
        self._iterator = iter(self.records)
        return self

    async def __anext__(self) -> FakeRecord:
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration from None


def settings(**overrides: Any) -> EventBusSettings:
    values: dict[str, Any] = {
        "bootstrap_servers": "localhost:9092",
        "consumer_group": "worker-events",
        "retry_backoff_seconds": 0.001,
        "retry_backoff_cap_seconds": 0.001,
    }
    values.update(overrides)
    return EventBusSettings(**values)


def registry() -> EventRegistry:
    catalogue = EventRegistry()
    catalogue.register("job.generation.requested", 1, "job", JobRequested)
    return catalogue


def envelope(event_type: str = "job.generation.requested", **overrides: Any) -> EventEnvelope:
    values: dict[str, Any] = {
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": OCCURRED_AT,
        "organization_id": ORGANIZATION_ID,
        "subject": "job-1",
        "correlation_id": CORRELATION_ID,
        "producer": "ai-engine",
        "payload": {"job_id": "job-1"},
    }
    values.update(overrides)
    return EventEnvelope(**values)


def build_consumer(
    runtime: FakeRuntime,
    publisher: FakePublisher,
    **setting_overrides: Any,
) -> EventConsumer:
    return EventConsumer(
        settings(**setting_overrides),
        registry(),
        runtime,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
    )


def test_a_registered_event_runs_its_handler_once_and_commits() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    handled: list[EventEnvelope] = []

    async def handler(received: EventEnvelope, payload: BaseModel, session: Any) -> None:
        handled.append(received)

    consumer.register_handler("job.generation.requested", 1, handler)
    kafka = FakeKafkaConsumer([FakeRecord(envelope().to_bytes())])

    asyncio.run(_run(consumer, kafka))

    assert len(handled) == 1
    assert isinstance(handled[0], EventEnvelope)
    assert runtime.transactions == 1
    assert publisher.dead_letters == []
    assert kafka.commits == 1


def test_the_same_event_delivered_twice_runs_the_work_once() -> None:
    runtime, publisher = FakeRuntime(claims=[CLAIMED, None]), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    handled: list[EventEnvelope] = []

    async def handler(received: EventEnvelope, payload: BaseModel, session: Any) -> None:
        handled.append(received)

    consumer.register_handler("job.generation.requested", 1, handler)
    delivered = envelope()
    kafka = FakeKafkaConsumer(
        [FakeRecord(delivered.to_bytes()), FakeRecord(delivered.to_bytes())]
    )

    asyncio.run(_run(consumer, kafka))

    assert len(handled) == 1
    assert runtime.transactions == 2
    assert publisher.dead_letters == []
    assert kafka.commits == 2


def test_unreadable_bytes_go_straight_to_the_dead_letter_topic() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    kafka = FakeKafkaConsumer([FakeRecord(b"not-an-envelope")])

    asyncio.run(_run(consumer, kafka))

    assert publisher.dead_letters == [(TOPIC, b"not-an-envelope", DeadLetterReason.UNDECODABLE)]
    assert runtime.transactions == 0
    assert kafka.commits == 1


def test_an_unregistered_event_type_is_dead_lettered_without_retry() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    record = FakeRecord(envelope(event_type="job.generation.cancelled").to_bytes())

    asyncio.run(_run(consumer, FakeKafkaConsumer([record])))

    assert publisher.dead_letters[0][2] is DeadLetterReason.UNKNOWN_EVENT_TYPE
    assert runtime.transactions == 0


def test_a_payload_that_breaks_the_contract_is_dead_lettered_without_retry() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    record = FakeRecord(envelope(payload={"wrong_field": "x"}).to_bytes())

    asyncio.run(_run(consumer, FakeKafkaConsumer([record])))

    assert publisher.dead_letters[0][2] is DeadLetterReason.CONTRACT_MISMATCH
    assert runtime.transactions == 0


def test_a_failing_handler_is_retried_to_the_limit_then_dead_lettered() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher, max_delivery_attempts=3)
    attempts: list[int] = []

    async def handler(received: EventEnvelope, payload: BaseModel, session: Any) -> None:
        attempts.append(1)
        raise RuntimeError("handler exploded do-not-print")

    consumer.register_handler("job.generation.requested", 1, handler)
    kafka = FakeKafkaConsumer([FakeRecord(envelope().to_bytes())])

    asyncio.run(_run(consumer, kafka))

    assert len(attempts) == 3
    assert runtime.transactions == 3
    assert runtime.rolled_back == 3
    assert publisher.dead_letters[0][2] is DeadLetterReason.HANDLER_FAILED
    assert kafka.commits == 1


def test_the_reader_carries_on_after_a_poison_record() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    handled: list[EventEnvelope] = []

    async def handler(received: EventEnvelope, payload: BaseModel, session: Any) -> None:
        handled.append(received)

    consumer.register_handler("job.generation.requested", 1, handler)
    kafka = FakeKafkaConsumer(
        [FakeRecord(b"not-an-envelope"), FakeRecord(envelope().to_bytes())]
    )

    asyncio.run(_run(consumer, kafka))

    assert len(handled) == 1
    assert len(publisher.dead_letters) == 1
    assert kafka.commits == 2


def test_an_event_with_no_registered_handler_is_left_unclaimed() -> None:
    runtime, publisher = FakeRuntime(), FakePublisher()
    consumer = build_consumer(runtime, publisher)
    kafka = FakeKafkaConsumer([FakeRecord(envelope().to_bytes())])

    asyncio.run(_run(consumer, kafka))

    assert runtime.transactions == 0
    assert publisher.dead_letters == []
    assert kafka.commits == 1


def test_registering_a_handler_for_an_unknown_event_type_fails_at_wiring_time() -> None:
    consumer = build_consumer(FakeRuntime(), FakePublisher())

    async def handler(received: EventEnvelope, payload: BaseModel, session: Any) -> None:
        return None

    with pytest.raises(UnknownEventTypeError):
        consumer.register_handler("job.generation.cancelled", 1, handler)


def test_backoff_never_exceeds_the_configured_cap() -> None:
    consumer = build_consumer(
        FakeRuntime(),
        FakePublisher(),
        retry_backoff_seconds=1.0,
        retry_backoff_cap_seconds=2.0,
    )

    assert all(0 <= consumer._backoff_seconds(attempt) <= 2.0 for attempt in range(1, 8))


def test_start_subscribes_to_every_registered_topic_and_stop_closes_it() -> None:
    consumer = build_consumer(FakeRuntime(), FakePublisher())
    kafka = FakeKafkaConsumer([])

    asyncio.run(_start_and_stop(consumer, kafka))

    assert kafka.started is True
    assert kafka.stopped is True
    assert consumer._registry.topics("trialscribe") == (TOPIC,)


async def _run(consumer: EventConsumer, kafka: FakeKafkaConsumer) -> None:
    await consumer.start(consumer=kafka)
    await consumer.run()


async def _start_and_stop(consumer: EventConsumer, kafka: FakeKafkaConsumer) -> None:
    await consumer.start(consumer=kafka)
    await consumer.stop()
