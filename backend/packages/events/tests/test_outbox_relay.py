import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from trialscribe_events.models.outbox_event import OutboxEvent
from trialscribe_events.outbox_relay import OutboxRelay
from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.exceptions import EventPublishError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000071")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000072")
OCCURRED_AT = datetime(2026, 8, 9, 15, 0, 0, tzinfo=UTC)
BATCH_SIZE = 10
POLL_SECONDS = 0.01


class WorkRequested(BaseModel):
    work_id: str


def stored_event(work_id: str = "work-1") -> OutboxEvent:
    registry = EventRegistry()
    registry.register("probe.work.requested", 1, "probe", WorkRequested)
    envelope = registry.build(
        event_type="probe.work.requested",
        version=1,
        organization_id=ORGANIZATION_ID,
        subject=work_id,
        correlation_id=CORRELATION_ID,
        producer="worker-service",
        payload=WorkRequested(work_id=work_id),
        occurred_at=OCCURRED_AT,
    )
    return OutboxEvent(
        id=uuid4(),
        topic="trialscribe.probe.v1",
        partition_key=envelope.partition_key(),
        payload=envelope.to_bytes(),
        headers={name: value.decode("utf-8") for name, value in envelope.headers()},
        attempts=0,
        published_at=None,
    )


class FakeOutboxRepository:
    """Apply the same guards the real statements carry: pending rows only."""

    store: Any = None

    def __init__(self, _session: Any) -> None:
        pass

    async def claim_unpublished(self, limit: int) -> list[OutboxEvent]:
        pending = [row for row in type(self).store.rows if row.published_at is None]
        type(self).store.claims.append(limit)
        return pending[:limit]

    async def mark_published(self, ids: list[UUID], now: datetime) -> list[UUID]:
        settled = []
        for row in type(self).store.rows:
            if row.id in ids and row.published_at is None:
                row.published_at = now
                settled.append(row.id)
        return settled

    async def record_failure(self, ids: list[UUID], now: datetime) -> list[UUID]:
        counted = []
        for row in type(self).store.rows:
            if row.id in ids and row.published_at is None:
                row.attempts += 1
                counted.append(row.id)
        return counted


class Store:
    def __init__(self, rows: list[OutboxEvent]) -> None:
        self.rows = rows
        self.claims: list[int] = []


class FakeRuntime:
    @asynccontextmanager
    async def transaction(self) -> Any:
        yield None


class FakePublisher:
    def __init__(self, fail_topics: set[str] | None = None) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, Any]] = []
        self.fail_topics = fail_topics or set()

    async def publish_raw(
        self,
        topic: str,
        value: bytes,
        key: bytes | None = None,
        headers: Any = None,
    ) -> None:
        if topic in self.fail_topics:
            raise EventPublishError("event could not be published")
        self.sent.append((topic, value, key, headers))


def build_relay(
    rows: list[OutboxEvent],
    publisher: FakePublisher,
    monkeypatch: Any,
) -> tuple[OutboxRelay, Store]:
    store = Store(rows)
    FakeOutboxRepository.store = store
    monkeypatch.setattr(
        "trialscribe_events.outbox_relay.OutboxRepository",
        FakeOutboxRepository,
    )
    relay = OutboxRelay(
        FakeRuntime(),  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        BATCH_SIZE,
        POLL_SECONDS,
    )
    return relay, store


def test_a_pending_event_is_delivered_exactly_as_it_was_stored(
    monkeypatch: Any,
) -> None:
    row = stored_event()
    publisher = FakePublisher()
    relay, store = build_relay([row], publisher, monkeypatch)

    result = asyncio.run(relay.drain_once())

    assert result.published == 1
    assert result.failed == 0
    topic, value, key, headers = publisher.sent[0]
    assert topic == row.topic
    assert value == row.payload
    assert key == row.partition_key
    assert dict(headers)["x-trialscribe-event-type"] == b"probe.work.requested"
    assert store.rows[0].published_at is not None


def test_an_event_is_settled_only_once_it_really_reached_the_broker(
    monkeypatch: Any,
) -> None:
    row = stored_event()
    publisher = FakePublisher(fail_topics={row.topic})
    relay, store = build_relay([row], publisher, monkeypatch)

    result = asyncio.run(relay.drain_once())

    assert result.published == 0
    assert result.failed == 1
    assert store.rows[0].published_at is None
    assert store.rows[0].attempts == 1


def test_a_failed_event_is_delivered_on_the_next_pass(monkeypatch: Any) -> None:
    row = stored_event()
    publisher = FakePublisher(fail_topics={row.topic})
    relay, store = build_relay([row], publisher, monkeypatch)

    asyncio.run(relay.drain_once())
    publisher.fail_topics.clear()
    result = asyncio.run(relay.drain_once())

    assert result.published == 1
    assert store.rows[0].published_at is not None
    assert store.rows[0].attempts == 1


def test_one_bad_event_never_holds_up_the_rest_of_the_batch(
    monkeypatch: Any,
) -> None:
    good, bad = stored_event("good"), stored_event("bad")
    bad.topic = "trialscribe.broken.v1"
    publisher = FakePublisher(fail_topics={bad.topic})
    relay, store = build_relay([good, bad], publisher, monkeypatch)

    result = asyncio.run(relay.drain_once())

    assert (result.published, result.failed) == (1, 1)
    assert store.rows[0].published_at is not None
    assert store.rows[1].published_at is None


def test_a_settled_event_is_never_sent_a_second_time(monkeypatch: Any) -> None:
    row = stored_event()
    publisher = FakePublisher()
    relay, _ = build_relay([row], publisher, monkeypatch)

    asyncio.run(relay.drain_once())
    result = asyncio.run(relay.drain_once())

    assert result.published == 0
    assert len(publisher.sent) == 1


def test_an_empty_outbox_costs_nothing(monkeypatch: Any) -> None:
    publisher = FakePublisher()
    relay, _ = build_relay([], publisher, monkeypatch)

    result = asyncio.run(relay.drain_once())

    assert (result.published, result.failed) == (0, 0)
    assert bool(result) is False
    assert publisher.sent == []


def test_a_claim_never_asks_for_more_than_its_batch(monkeypatch: Any) -> None:
    publisher = FakePublisher()
    relay, store = build_relay([stored_event()], publisher, monkeypatch)

    asyncio.run(relay.drain_once())

    assert store.claims == [BATCH_SIZE]


def test_the_relay_drains_until_it_is_asked_to_stop(monkeypatch: Any) -> None:
    async def scenario() -> tuple[int, list[Any]]:
        rows = [stored_event(f"work-{index}") for index in range(3)]
        publisher = FakePublisher()
        relay, _ = build_relay(rows, publisher, monkeypatch)
        stop = asyncio.Event()

        running = asyncio.create_task(relay.run(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(running, timeout=5)
        return len(publisher.sent), publisher.sent

    delivered, sent = asyncio.run(scenario())

    assert delivered == 3
    assert len({value for _, value, _, _ in sent}) == 3


def test_a_broken_outbox_does_not_end_the_relay(monkeypatch: Any) -> None:
    async def scenario() -> bool:
        publisher = FakePublisher()
        relay, _ = build_relay([], publisher, monkeypatch)

        async def exploding_drain() -> Any:
            raise RuntimeError("database unavailable do-not-print")

        relay.drain_once = exploding_drain  # type: ignore[method-assign]
        stop = asyncio.Event()
        running = asyncio.create_task(relay.run(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(running, timeout=5)
        return running.done()

    assert asyncio.run(scenario()) is True
