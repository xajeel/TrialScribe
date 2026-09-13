import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.dialects import postgresql

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.models.outbox_event import OutboxEvent
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.outbox import OutboxRepository

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000061")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000062")
OCCURRED_AT = datetime(2026, 8, 9, 14, 0, 0, tzinfo=UTC)
TOPIC = "trialscribe.job.v1"
MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "database"
    / "migrations"
    / "versions"
    / "0011_create_event_outbox_table.py"
)


class WorkRequested(BaseModel):
    work_id: str


class RecordingSession:
    """Capture what a repository builds, without executing anything."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self.flushes = 0

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        raise _Captured


class _Captured(Exception):
    """Raised to stop a repository call once its statement was captured."""


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def capture(call: Any) -> str:
    session = RecordingSession()
    repository = OutboxRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(call(repository))
    except _Captured:
        pass
    assert session.statements, "no statement was built"
    return compiled(session.statements[-1])


def envelope() -> EventEnvelope:
    registry = EventRegistry()
    registry.register("probe.work.requested", 1, "probe", WorkRequested)
    return registry.build(
        event_type="probe.work.requested",
        version=1,
        organization_id=ORGANIZATION_ID,
        subject="work-1",
        correlation_id=CORRELATION_ID,
        producer="worker-service",
        payload=WorkRequested(work_id="work-1"),
        occurred_at=OCCURRED_AT,
    )


def test_an_enqueued_event_stores_exactly_the_bytes_the_broker_will_receive() -> None:
    session = RecordingSession()
    original = envelope()

    record = asyncio.run(OutboxRepository(session).enqueue(TOPIC, original))  # type: ignore[arg-type]

    assert record.payload == original.to_bytes()
    assert record.partition_key == original.partition_key()
    assert record.topic == TOPIC
    assert session.added == [record]
    assert session.flushes == 1


def test_a_stored_event_can_be_read_back_into_the_envelope_it_came_from() -> None:
    original = envelope()

    record = asyncio.run(OutboxRepository(RecordingSession()).enqueue(TOPIC, original))  # type: ignore[arg-type]

    assert EventEnvelope.from_bytes(record.payload) == original


def test_routing_headers_survive_as_text_and_convert_back_to_bytes() -> None:
    original = envelope()

    record = asyncio.run(OutboxRepository(RecordingSession()).enqueue(TOPIC, original))  # type: ignore[arg-type]

    restored = [(name, value.encode("utf-8")) for name, value in record.headers.items()]
    assert restored == original.headers()


def test_claiming_takes_the_oldest_pending_events_and_skips_locked_rows() -> None:
    sql = capture(lambda repository: repository.claim_unpublished(50))

    assert "published_at IS NULL" in sql
    assert "ORDER BY trialscribe.event_outbox.created_at" in sql
    assert "FOR UPDATE" in sql
    assert "SKIP LOCKED" in sql
    assert "LIMIT" in sql


def test_marking_published_only_ever_settles_a_pending_event() -> None:
    sql = capture(
        lambda repository: repository.mark_published([uuid4()], OCCURRED_AT)
    )

    assert "published_at IS NULL" in sql
    assert "SET published_at=" in sql
    assert "RETURNING trialscribe.event_outbox.id" in sql


def test_a_failed_delivery_counts_the_attempt_and_leaves_the_event_pending() -> None:
    sql = capture(
        lambda repository: repository.record_failure([uuid4()], OCCURRED_AT)
    )

    assert "attempts=(trialscribe.event_outbox.attempts + " in sql
    assert "published_at IS NULL" in sql
    assert "published_at=" not in sql.split("SET")[1].split("WHERE")[0]


def test_settling_nothing_touches_the_database_at_all() -> None:
    session = RecordingSession()
    repository = OutboxRepository(session)  # type: ignore[arg-type]

    assert asyncio.run(repository.mark_published([], OCCURRED_AT)) == []
    assert asyncio.run(repository.record_failure([], OCCURRED_AT)) == []
    assert session.statements == []


def test_the_outbox_declares_no_foreign_key_it_cannot_resolve() -> None:
    """This package cannot see the tables of the services that write to it.

    A foreign key declared here would fail to resolve the moment a statement is
    built, exactly as it did for the jobs table (bug B27).
    """

    assert [
        column.name for column in OutboxEvent.__table__.columns if column.foreign_keys
    ] == []
    assert OutboxEvent.__table__.schema == "trialscribe"


def test_the_pending_index_covers_only_undelivered_events() -> None:
    index = {index.name: index for index in OutboxEvent.__table__.indexes}
    source = MIGRATION.read_text()

    assert "ix_event_outbox_unpublished" in index
    assert [
        column.name for column in index["ix_event_outbox_unpublished"].columns
    ] == ["created_at", "id"]
    assert 'postgresql_where=sa.text("published_at IS NULL")' in source
