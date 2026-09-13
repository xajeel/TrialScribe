import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.models.processed_event import ProcessedEvent
from trialscribe_events.repositories.processed_events import ProcessedEventRepository

EVENT_ID = UUID("00000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000003")
CONSUMER_GROUP = "worker-events"


class FakeResult:
    """Model PostgreSQL's INSERT ... ON CONFLICT DO NOTHING ... RETURNING contract:
    one row when this statement inserted it, no rows when it was already there."""

    def __init__(self, returned: UUID | None) -> None:
        self._returned = returned

    def scalar_one_or_none(self) -> UUID | None:
        return self._returned


class FakeSession:
    def __init__(self, returned: UUID | None = EVENT_ID) -> None:
        self.returned = returned
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.returned)


def envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=EVENT_ID,
        event_type="job.generation.requested",
        event_version=1,
        occurred_at=datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC),
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload={"job_id": "job-1"},
    )


def claim(session: FakeSession) -> bool:
    repository = ProcessedEventRepository(session)  # type: ignore[arg-type]
    return asyncio.run(repository.claim(CONSUMER_GROUP, envelope()))


def test_table_is_keyed_by_consumer_group_and_event() -> None:
    table = ProcessedEvent.__table__

    assert table.schema == "trialscribe"
    assert table.name == "processed_events"
    assert [column.name for column in table.primary_key.columns] == [
        "consumer_group",
        "event_id",
    ]
    assert "ix_processed_events_created_at" in {index.name for index in table.indexes}


def test_first_claim_of_an_event_reports_the_work_should_run() -> None:
    session = FakeSession(returned=EVENT_ID)

    assert claim(session) is True


def test_repeat_claim_of_the_same_event_reports_the_work_was_already_done() -> None:
    session = FakeSession(returned=None)

    assert claim(session) is False


def test_claim_asks_the_database_which_call_won_instead_of_counting_rows() -> None:
    session = FakeSession()

    claim(session)

    statement = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "RETURNING trialscribe.processed_events.event_id" in statement


def test_claim_inserts_the_event_facts_and_ignores_a_conflict() -> None:
    session = FakeSession()

    claim(session)

    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    statement = str(compiled)
    assert "INSERT INTO trialscribe.processed_events" in statement
    assert "ON CONFLICT (consumer_group, event_id) DO NOTHING" in statement
    assert compiled.params["consumer_group"] == CONSUMER_GROUP
    assert compiled.params["event_id"] == EVENT_ID
    assert compiled.params["event_type"] == "job.generation.requested"
    assert compiled.params["organization_id"] == ORGANIZATION_ID
    assert "job-1" not in str(compiled.params)
