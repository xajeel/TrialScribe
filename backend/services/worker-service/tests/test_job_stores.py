import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.utils.constant import (
    JOB_CANCEL_KEY_PREFIX,
    JOB_PROGRESS_KEY_PREFIX,
)
from trialscribe_worker.utils.enum import JobErrorCode, JobStatus

JOB_ID = UUID("00000000-0000-4000-8000-000000000021")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000022")
NOW = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)
TTL_SECONDS = 3600


class FakeKeyValueStore:
    """A dictionary that answers exactly the three commands the store uses."""

    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values: dict[str, Any] = dict(values or {})
        self.expiries: dict[str, int | None] = {}
        self.deleted: list[tuple[str, ...]] = []

    async def get(self, name: str) -> Any:
        return self.values.get(name)

    async def set(self, name: str, value: str, ex: int | None = None) -> Any:
        self.values[name] = value
        self.expiries[name] = ex
        return True

    async def delete(self, *names: str) -> Any:
        self.deleted.append(names)
        for name in names:
            self.values.pop(name, None)
        return len(names)


def store(values: dict[str, Any] | None = None) -> tuple[JobProgressStore, FakeKeyValueStore]:
    client = FakeKeyValueStore(values)
    return JobProgressStore(client, TTL_SECONDS), client


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


class RecordingSession:
    """Capture the statement a repository builds without executing it."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        raise _Captured

    def add(self, instance: Any) -> None:
        self.statements.append(instance)

    async def flush(self) -> None:
        return None


class _Captured(Exception):
    """Raised to stop a repository call once its statement was captured."""


def capture(call: Any) -> str:
    session = RecordingSession()
    repository = JobRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(call(repository))
    except _Captured:
        pass
    assert session.statements, "no statement was built"
    return compiled(session.statements[-1])


def test_progress_and_cancel_keys_are_namespaced_per_job() -> None:
    progress, _ = store()

    assert progress.progress_key(JOB_ID) == f"{JOB_PROGRESS_KEY_PREFIX}{JOB_ID}"
    assert progress.cancel_key(JOB_ID) == f"{JOB_CANCEL_KEY_PREFIX}{JOB_ID}"


def test_live_progress_round_trips_and_carries_the_configured_lifetime() -> None:
    progress, client = store()

    asyncio.run(progress.set_progress(JOB_ID, 42))

    assert asyncio.run(progress.get_progress(JOB_ID)) == 42
    assert client.expiries[progress.progress_key(JOB_ID)] == TTL_SECONDS


def test_a_progress_value_stored_as_bytes_is_still_read() -> None:
    progress, _ = store({f"{JOB_PROGRESS_KEY_PREFIX}{JOB_ID}": b"77"})

    assert asyncio.run(progress.get_progress(JOB_ID)) == 77


def test_missing_unreadable_and_impossible_progress_all_read_as_unknown() -> None:
    for stored in (None, "not-a-number", "-1", "101", ""):
        values = {} if stored is None else {f"{JOB_PROGRESS_KEY_PREFIX}{JOB_ID}": stored}
        progress, _ = store(values)

        assert asyncio.run(progress.get_progress(JOB_ID)) is None


def test_a_stop_request_is_visible_until_the_job_state_is_cleared() -> None:
    progress, client = store()

    assert asyncio.run(progress.is_cancelled(JOB_ID)) is False
    asyncio.run(progress.request_cancel(JOB_ID))
    assert asyncio.run(progress.is_cancelled(JOB_ID)) is True

    asyncio.run(progress.clear(JOB_ID))

    assert asyncio.run(progress.is_cancelled(JOB_ID)) is False
    assert client.deleted == [(progress.progress_key(JOB_ID), progress.cancel_key(JOB_ID))]


def test_claiming_a_job_names_every_status_it_is_willing_to_take_over() -> None:
    sql = capture(lambda repository: repository.claim(JOB_ID, NOW))

    assert "UPDATE trialscribe.jobs" in sql
    assert "status IN" in sql
    assert "attempt=(trialscribe.jobs.attempt + " in sql
    assert "RETURNING" in sql


def test_finishing_a_job_only_ever_replaces_a_running_one() -> None:
    sql = capture(
        lambda repository: repository.finish(
            JOB_ID,
            JobStatus.SUCCEEDED,
            NOW,
            error_code=None,
            progress=100,
        )
    )

    assert "WHERE trialscribe.jobs.id = " in sql
    assert "trialscribe.jobs.status = " in sql
    assert "greatest(trialscribe.jobs.progress" in sql
    assert "RETURNING trialscribe.jobs.id" in sql


def test_recording_progress_can_never_lower_it_and_returns_the_stop_stamp() -> None:
    sql = capture(lambda repository: repository.record_progress(JOB_ID, 30))

    assert "greatest(trialscribe.jobs.progress" in sql
    assert "RETURNING trialscribe.jobs.cancel_requested_at" in sql
    assert "status" not in sql.split("WHERE")[-1]


def test_marking_a_job_for_retry_only_applies_to_a_running_one() -> None:
    sql = capture(lambda repository: repository.mark_retrying(JOB_ID, NOW))

    assert "SET status=" in sql
    assert "RETURNING trialscribe.jobs.id" in sql


def test_cancelling_a_waiting_job_is_scoped_to_its_own_organization() -> None:
    sql = capture(
        lambda repository: repository.cancel_queued(ORGANIZATION_ID, JOB_ID, NOW)
    )

    assert "trialscribe.jobs.organization_id = " in sql
    assert "finished_at=" in sql
    assert "error_code=" in sql


def test_requesting_a_stop_never_touches_a_job_that_already_finished() -> None:
    sql = capture(
        lambda repository: repository.request_cancel(ORGANIZATION_ID, JOB_ID, NOW)
    )

    assert "status NOT IN" in sql
    assert "coalesce(trialscribe.jobs.cancel_requested_at" in sql


def test_the_terminal_error_codes_are_the_ones_the_table_accepts() -> None:
    accepted = {code.value for code in JobErrorCode}
    job_columns = {column.name for column in Job.__table__.columns}

    assert accepted == {"handler_failed", "unsupported_kind", "cancelled"}
    assert {"cancel_requested_at", "finished_at", "started_at"} <= job_columns
