from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from trialscribe_events.contracts.job import register_job_events
from trialscribe_events.config import EventBusSettings
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.models.outbox_event import OutboxEvent
from trialscribe_events.registry import EventRegistry

from trialscribe_worker.api.app import app
from trialscribe_worker.api.dependencies import (
    get_database_runtime,
    get_event_settings,
    get_now,
    get_outbox_relay,
    get_progress_store,
    get_registry,
)
from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.utils.enum import JobStatus

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000041")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000042")
NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
TTL_SECONDS = 3600
HEADERS = {
    "X-TrialScribe-Account-ID": str(ACCOUNT_ID),
    "X-TrialScribe-Organization-ID": str(ORGANIZATION_ID),
}


class FakeKeyValueStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get(self, name: str) -> Any:
        return self.values.get(name)

    async def set(self, name: str, value: str, ex: int | None = None) -> Any:
        self.values[name] = value
        return True

    async def delete(self, *names: str) -> Any:
        for name in names:
            self.values.pop(name, None)
        return len(names)


class FakeSession:
    """Stand in for a session; the repository is swapped out entirely."""


class FakeRuntime:
    def __init__(self) -> None:
        self.commits = 0

    @asynccontextmanager
    async def transaction(self) -> Any:
        yield FakeSession()
        self.commits += 1


class FakeJobRepository:
    """Apply exactly the status guards the real statements carry."""

    jobs: dict[UUID, Job] = {}

    def __init__(self, _session: Any) -> None:
        pass

    async def add(self, job: Job) -> Job:
        job.id = job.id or uuid4()
        job.created_at = NOW
        job.updated_at = NOW
        type(self).jobs[job.id] = job
        return job

    async def get(self, organization_id: UUID, job_id: UUID) -> Job | None:
        job = type(self).jobs.get(job_id)
        if job is None or job.organization_id != organization_id:
            return None
        return job

    async def cancel_queued(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> Job | None:
        job = await self.get(organization_id, job_id)
        if job is None or job.status != JobStatus.QUEUED.value:
            return None
        job.status = JobStatus.CANCELLED.value
        job.error_code = "cancelled"
        job.cancel_requested_at = now
        job.finished_at = now
        return job

    async def request_cancel(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> Job | None:
        job = await self.get(organization_id, job_id)
        if job is None or JobStatus(job.status).is_terminal():
            return None
        job.cancel_requested_at = job.cancel_requested_at or now
        return job


class FakeOutbox:
    """Record what the request stored beside its ticket."""

    stored: list[OutboxEvent] = []

    def __init__(self, _session: Any) -> None:
        pass

    async def enqueue(self, topic: str, envelope: EventEnvelope) -> OutboxEvent:
        record = OutboxEvent(
            topic=topic,
            partition_key=envelope.partition_key(),
            payload=envelope.to_bytes(),
            headers={name: value.decode("utf-8") for name, value in envelope.headers()},
        )
        type(self).stored.append(record)
        return record


class FakeRelay:
    """Stand in for the sweeper that hands stored events to the broker."""

    def __init__(self) -> None:
        self.drains = 0
        self.fail = False

    async def drain_once(self) -> int:
        self.drains += 1
        if self.fail:
            raise ConnectionError("broker unreachable do-not-print")
        return len(FakeOutbox.stored)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    FakeJobRepository.jobs = {}
    FakeOutbox.stored = []
    monkeypatch.setattr(
        "trialscribe_worker.api.jobs.JobRepository",
        FakeJobRepository,
    )
    monkeypatch.setattr(
        "trialscribe_worker.api.jobs.OutboxRepository",
        FakeOutbox,
    )
    client_store = FakeKeyValueStore()
    relay = FakeRelay()
    runtime = FakeRuntime()

    app.dependency_overrides[get_database_runtime] = lambda: runtime
    app.dependency_overrides[get_progress_store] = lambda: JobProgressStore(
        client_store,
        TTL_SECONDS,
    )
    app.dependency_overrides[get_outbox_relay] = lambda: relay
    app.dependency_overrides[get_registry] = lambda: register_job_events(EventRegistry())
    app.dependency_overrides[get_event_settings] = lambda: EventBusSettings(
        bootstrap_servers="localhost:9092",
    )
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        yield {
            "client": TestClient(app),
            "relay": relay,
            "outbox": FakeOutbox,
            "store": client_store,
            "runtime": runtime,
        }
    finally:
        app.dependency_overrides.clear()


def test_the_repository_swap_leaves_the_real_class_importable() -> None:
    assert JobRepository.__name__ == "JobRepository"


def test_requesting_a_job_is_accepted_and_announced(api: dict[str, Any]) -> None:
    response = api["client"].post(
        "/jobs",
        json={"kind": "probe", "parameters": {"steps": 2}},
        headers=HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["attempt"] == 0
    assert body["organization_id"] == str(ORGANIZATION_ID)
    assert len(api["outbox"].stored) == 1
    stored = EventEnvelope.from_bytes(api["outbox"].stored[0].payload)
    assert stored.subject == body["id"]
    assert api["relay"].drains == 1


def test_a_requested_job_can_be_read_back_with_its_live_progress(
    api: dict[str, Any],
) -> None:
    created = api["client"].post(
        "/jobs",
        json={"kind": "probe"},
        headers=HEADERS,
    ).json()
    api["store"].values[f"trialscribe:job:progress:{created['id']}"] = "35"

    response = api["client"].get(f"/jobs/{created['id']}", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["progress"] == 35


def test_a_waiting_job_can_be_cancelled(api: dict[str, Any]) -> None:
    created = api["client"].post(
        "/jobs",
        json={"kind": "probe"},
        headers=HEADERS,
    ).json()

    response = api["client"].post(f"/jobs/{created['id']}/cancel", headers=HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "cancelled"
    assert response.json()["error_code"] == "cancelled"


def test_cancelling_a_finished_job_is_a_conflict(api: dict[str, Any]) -> None:
    created = api["client"].post(
        "/jobs",
        json={"kind": "probe"},
        headers=HEADERS,
    ).json()
    job = FakeJobRepository.jobs[UUID(created["id"])]
    job.status = JobStatus.SUCCEEDED.value
    job.finished_at = NOW

    response = api["client"].post(f"/jobs/{created['id']}/cancel", headers=HEADERS)

    assert response.status_code == 409
    assert response.json() == {"detail": "job already finished"}


def test_an_unknown_job_is_not_found(api: dict[str, Any]) -> None:
    response = api["client"].get(f"/jobs/{uuid4()}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "job not found"}


def test_a_kind_this_worker_does_not_serve_is_rejected(api: dict[str, Any]) -> None:
    response = api["client"].post(
        "/jobs",
        json={"kind": "section-generation"},
        headers=HEADERS,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "job kind is not supported"}


def test_an_unreachable_broker_no_longer_costs_the_caller_their_job(
    api: dict[str, Any],
) -> None:
    """A committed ticket is a queued job, broker reachable or not.

    The message is already stored beside the ticket, so handing it over is the
    relay's job and its failure is not the caller's problem (bug B29).
    """

    api["relay"].fail = True

    response = api["client"].post("/jobs", json={"kind": "probe"}, headers=HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert len(api["outbox"].stored) == 1
    assert api["runtime"].commits == 1


def test_a_rejected_request_never_commits_its_ticket(api: dict[str, Any]) -> None:
    api["client"].post("/jobs", json={"kind": "section-generation"}, headers=HEADERS)

    assert api["runtime"].commits == 0
    assert api["outbox"].stored == []


def test_a_request_without_organization_context_is_refused(
    api: dict[str, Any],
) -> None:
    response = api["client"].post(
        "/jobs",
        json={"kind": "probe"},
        headers={"X-TrialScribe-Account-ID": str(ACCOUNT_ID)},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid organization context"}


def test_a_request_without_account_context_is_unauthenticated(
    api: dict[str, Any],
) -> None:
    response = api["client"].post(
        "/jobs",
        json={"kind": "probe"},
        headers={"X-TrialScribe-Organization-ID": str(ORGANIZATION_ID)},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid account context"}
