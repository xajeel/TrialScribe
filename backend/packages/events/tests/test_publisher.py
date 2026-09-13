import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from aiokafka.errors import TopicAlreadyExistsError
from prometheus_client import REGISTRY, generate_latest
from pydantic import BaseModel

from trialscribe_events.config import EventBusSettings
from trialscribe_events.publisher import EventPublisher, create_event_publisher
from trialscribe_events.registry import EventRegistry
from trialscribe_events.topics import ensure_topics
from trialscribe_events.utils.constant import DEAD_LETTER_REASON_HEADER
from trialscribe_events.utils.enum import DeadLetterReason
from trialscribe_events.utils.exceptions import EventError, EventPublishError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000003")
OCCURRED_AT = datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC)


def _published(result: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "trialscribe_events_published_total",
            {"result": result},
        )
        or 0.0
    )


class JobRequested(BaseModel):
    job_id: str


class SentRecord:
    def __init__(self, topic: str, value: bytes | None, key: bytes | None, headers: Any) -> None:
        self.topic = topic
        self.value = value
        self.key = key
        self.headers = headers


class FakeProducer:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[SentRecord] = []
        self.started = False
        self.stopped = False
        self.fail = fail

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(
        self,
        topic: str,
        value: bytes | None = None,
        key: bytes | None = None,
        headers: Any = None,
    ) -> None:
        if self.fail:
            raise RuntimeError("broker unreachable do-not-print")
        self.sent.append(SentRecord(topic, value, key, headers))


class FakeCreateResponse:
    def __init__(self, topic_errors: list[tuple[str, int]]) -> None:
        self.topic_errors = topic_errors


class FakeAdminClient:
    def __init__(
        self,
        existing: list[str] | None = None,
        topic_errors: list[tuple[str, int]] | None = None,
        raise_already_exists: bool = False,
    ) -> None:
        self.existing = existing or []
        self.topic_errors = topic_errors
        self.raise_already_exists = raise_already_exists
        self.started = False
        self.closed = False
        self.created: list[Any] = []

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def list_topics(self) -> list[str]:
        return self.existing

    async def create_topics(self, new_topics: list[Any]) -> FakeCreateResponse:
        self.created = new_topics
        if self.raise_already_exists:
            raise TopicAlreadyExistsError("already exists")
        errors = self.topic_errors
        if errors is None:
            errors = [(topic.name, 0) for topic in new_topics]
        return FakeCreateResponse(errors)


def settings() -> EventBusSettings:
    return EventBusSettings(bootstrap_servers="localhost:9092", client_id="test-client")


def registry() -> EventRegistry:
    catalogue = EventRegistry()
    catalogue.register("job.generation.requested", 1, "job", JobRequested)
    return catalogue


def build_publisher(producer: FakeProducer) -> EventPublisher:
    return EventPublisher(producer, registry(), settings())  # type: ignore[arg-type]


def envelope():
    return registry().build(
        event_type="job.generation.requested",
        version=1,
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload=JobRequested(job_id="job-1"),
        occurred_at=OCCURRED_AT,
    )


def test_publish_sends_to_the_registered_topic_with_subject_key_and_headers() -> None:
    producer = FakeProducer()
    publisher = build_publisher(producer)
    before = _published("ok")

    asyncio.run(publisher.publish(envelope()))

    assert len(producer.sent) == 1
    record = producer.sent[0]
    assert record.topic == "trialscribe.job.v1"
    assert record.key == b"job-1"
    assert dict(record.headers)["x-trialscribe-event-type"] == b"job.generation.requested"
    assert b"job-1" in (record.value or b"")
    assert _published("ok") == before + 1
    body = generate_latest().decode()
    assert "organization_id=" not in body
    assert "offset=" not in body
    assert "partition=" not in body


def test_start_and_stop_pass_through_to_the_producer() -> None:
    producer = FakeProducer()
    publisher = build_publisher(producer)

    asyncio.run(publisher.start())
    asyncio.run(publisher.stop())

    assert producer.started is True
    assert producer.stopped is True


def test_publish_failure_is_reported_without_leaking_broker_text() -> None:
    publisher = build_publisher(FakeProducer(fail=True))
    before = _published("error")

    with pytest.raises(EventPublishError) as error:
        asyncio.run(publisher.publish(envelope()))

    assert str(error.value) == "event could not be published"
    assert "do-not-print" not in str(error.value)
    assert _published("error") == before + 1


def test_dead_letter_sends_the_untouched_record_to_the_dlq_topic() -> None:
    producer = FakeProducer()
    publisher = build_publisher(producer)

    asyncio.run(
        publisher.publish_dead_letter(
            "trialscribe.job.v1",
            b"corrupt-bytes",
            DeadLetterReason.UNDECODABLE,
            key=b"job-1",
        )
    )

    record = producer.sent[0]
    assert record.topic == "trialscribe.job.v1.dlq"
    assert record.value == b"corrupt-bytes"
    assert record.key == b"job-1"
    assert dict(record.headers)[DEAD_LETTER_REASON_HEADER] == b"undecodable"


def test_dead_letter_failure_is_raised_so_the_record_can_be_redelivered() -> None:
    publisher = build_publisher(FakeProducer(fail=True))

    with pytest.raises(EventPublishError) as error:
        asyncio.run(
            publisher.publish_dead_letter(
                "trialscribe.job.v1",
                b"corrupt-bytes",
                DeadLetterReason.HANDLER_FAILED,
            )
        )

    assert str(error.value) == "event could not be published"
    assert "do-not-print" not in str(error.value)


def test_created_producer_is_idempotent_and_waits_for_all_replicas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    class RecordingProducer(FakeProducer):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__()
            recorded.update(kwargs)

    monkeypatch.setattr("trialscribe_events.publisher.AIOKafkaProducer", RecordingProducer)

    publisher = create_event_publisher(settings(), registry())

    assert isinstance(publisher, EventPublisher)
    assert recorded["bootstrap_servers"] == "localhost:9092"
    assert recorded["client_id"] == "test-client"
    assert recorded["enable_idempotence"] is True
    assert recorded["acks"] == "all"
    assert recorded["request_timeout_ms"] == 10000


def test_ensure_topics_creates_each_topic_with_its_dead_letter_companion() -> None:
    admin = FakeAdminClient()

    created = asyncio.run(
        ensure_topics(settings(), ["trialscribe.job.v1"], admin_client=admin)  # type: ignore[arg-type]
    )

    assert created == ("trialscribe.job.v1", "trialscribe.job.v1.dlq")
    assert [topic.num_partitions for topic in admin.created] == [3, 3]
    assert [topic.replication_factor for topic in admin.created] == [1, 1]
    assert admin.closed is True


def test_ensure_topics_skips_topics_that_already_exist() -> None:
    admin = FakeAdminClient(existing=["trialscribe.job.v1", "trialscribe.job.v1.dlq"])

    created = asyncio.run(
        ensure_topics(settings(), ["trialscribe.job.v1"], admin_client=admin)  # type: ignore[arg-type]
    )

    assert created == ()
    assert admin.created == []
    assert admin.closed is True


def test_ensure_topics_tolerates_a_concurrent_creation_race() -> None:
    admin = FakeAdminClient(raise_already_exists=True)

    created = asyncio.run(
        ensure_topics(settings(), ["trialscribe.job.v1"], admin_client=admin)  # type: ignore[arg-type]
    )

    assert created == ()
    assert admin.closed is True


def test_ensure_topics_reports_any_other_broker_error_and_still_closes() -> None:
    admin = FakeAdminClient(topic_errors=[("trialscribe.job.v1", 41)])

    with pytest.raises(EventError):
        asyncio.run(
            ensure_topics(settings(), ["trialscribe.job.v1"], admin_client=admin)  # type: ignore[arg-type]
        )

    assert admin.closed is True
