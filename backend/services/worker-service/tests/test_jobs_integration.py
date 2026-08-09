import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import DatabaseRuntime, create_database_runtime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.consumer import EventConsumer
from trialscribe_events.contracts.job import register_job_events
from trialscribe_events.publisher import EventPublisher, create_event_publisher
from trialscribe_events.outbox_relay import OutboxRelay
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.outbox import OutboxRepository
from trialscribe_events.topics import ensure_topics
from trialscribe_events.utils.constant import (
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
)

from trialscribe_worker.config import WorkerRedisSettings, WorkerSettings
from trialscribe_worker.pipelines.probe import probe_pipeline
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.services.job_runner import JobRunner
from trialscribe_worker.services.jobs import JobService
from trialscribe_worker.utils.enum import JobKind, JobStatus
from trialscribe_worker.utils.exceptions import JobAttemptFailedError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_JOBS_INTEGRATION") != "1",
        reason="requires the isolated PostgreSQL, Redis, and Kafka test project",
    ),
]

CONSUME_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3


def run_identifier() -> str:
    return uuid.uuid4().hex[:12]


def event_settings(identifier: str, **overrides: Any) -> EventBusSettings:
    values: dict[str, Any] = {
        "bootstrap_servers": os.environ["EVENTS_BOOTSTRAP_SERVERS"],
        "topic_prefix": f"trialscribe-jobs-{identifier}",
        "client_id": f"jobs-it-{identifier}",
        "consumer_group": f"jobs-it-{identifier}",
        "topic_partitions": 1,
        "topic_replication_factor": 1,
        "max_delivery_attempts": MAX_ATTEMPTS,
        "retry_backoff_seconds": 0.05,
        "retry_backoff_cap_seconds": 0.2,
    }
    values.update(overrides)
    return EventBusSettings(**values)


class Tenant:
    """One organization, account, and conversation the jobs can belong to."""

    def __init__(self) -> None:
        self.organization_id = uuid.uuid4()
        self.account_id = uuid.uuid4()
        self.conversation_id = uuid.uuid4()


async def seed_tenant(runtime: DatabaseRuntime) -> Tenant:
    tenant = Tenant()
    async with runtime.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO trialscribe.accounts (id, email, password_hash) "
                "VALUES (:id, :email, 'x')"
            ),
            {"id": tenant.account_id, "email": f"{tenant.account_id}@example.test"},
        )
        await session.execute(
            text("INSERT INTO trialscribe.organizations (id, name) VALUES (:id, :name)"),
            {"id": tenant.organization_id, "name": f"org-{tenant.organization_id.hex[:8]}"},
        )
        await session.execute(
            text(
                "INSERT INTO trialscribe.conversations "
                "(id, organization_id, owner_account_id, title) "
                "VALUES (:id, :organization_id, :account_id, 'integration')"
            ),
            {
                "id": tenant.conversation_id,
                "organization_id": tenant.organization_id,
                "account_id": tenant.account_id,
            },
        )
    return tenant


class Backbone:
    """Everything one integration scenario needs, opened and closed together."""

    def __init__(self, identifier: str, **setting_overrides: Any) -> None:
        self.identifier = identifier
        self.settings = event_settings(identifier, **setting_overrides)
        self.worker_settings = WorkerSettings(progress_persist_step=1)
        self.registry = register_job_events(EventRegistry())
        self.runtime: DatabaseRuntime
        self.redis: Redis
        self.publisher: EventPublisher
        self.consumer: EventConsumer
        self.progress: JobProgressStore
        self.handled: list[UUID] = []

    async def open(self) -> None:
        self.runtime = create_database_runtime(DatabaseSettings())
        self.redis = Redis.from_url(
            WorkerRedisSettings().connection_url(),
            decode_responses=False,
        )
        self.progress = JobProgressStore(self.redis, 3600)
        self.publisher = create_event_publisher(self.settings, self.registry)
        self.relay = OutboxRelay(self.runtime, self.publisher, 100, 0.05)
        await ensure_topics(
            self.settings,
            list(self.registry.topics(self.settings.topic_prefix)),
        )
        await self.publisher.start()

        runner = JobRunner(
            self.runtime,
            self.progress,
            self.worker_settings,
            self.settings,
            {JobKind.PROBE: probe_pipeline},
        )

        async def handler(envelope: Any, payload: Any, session: Any) -> None:
            self.handled.append(UUID(envelope.subject))
            await runner.handle(envelope, payload, session)

        self.consumer = EventConsumer(
            self.settings,
            self.registry,
            self.runtime,
            self.publisher,
        )
        self.consumer.register_handler(
            JOB_REQUESTED_EVENT_TYPE,
            JOB_EVENT_VERSION,
            handler,
        )
        await self.consumer.start()

    async def close(self) -> None:
        await self.consumer.stop()
        await self.publisher.stop()
        await self.redis.aclose()
        await self.runtime.dispose()

    def _service(self, session: Any) -> JobService:
        return JobService(
            JobRepository(session),
            self.progress,
            OutboxRepository(session),
            self.registry,
            self.settings.topic_prefix,
        )

    async def request(self, tenant: Tenant, *, hand_over: bool = True, **parameters: Any) -> UUID:
        async with self.runtime.transaction() as session:
            response = await self._service(session).request_job(
                tenant.organization_id,
                tenant.account_id,
                JobCreateRequest(
                    kind=JobKind.PROBE.value,
                    conversation_id=tenant.conversation_id,
                    parameters=parameters,
                ),
                datetime.now(UTC),
            )
        if hand_over:
            await self.relay.drain_once()
        return response.id

    async def records(self, expected: int, timeout: float) -> list[Any]:
        """Collect records without settling them, so a test can replay one."""

        collected: list[Any] = []
        deadline = asyncio.get_running_loop().time() + timeout
        while len(collected) < expected and asyncio.get_running_loop().time() < deadline:
            batches = await self.consumer._consumer.getmany(timeout_ms=500)
            for records in batches.values():
                collected.extend(records)
        return collected

    async def drain(self, expected: int, timeout: float) -> int:
        settled = 0
        for record in await self.records(expected, timeout):
            with_retry = self.consumer.process(record)
            try:
                await with_retry
            except JobAttemptFailedError:
                pass
            await self.consumer._consumer.commit()
            settled += 1
        return settled

    async def job_row(self, job_id: UUID) -> dict[str, Any]:
        async with self.runtime.transaction() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, attempt, progress, error_code, started_at, "
                        "finished_at FROM trialscribe.jobs WHERE id = :id"
                    ),
                    {"id": job_id},
                )
            ).mappings().one()
        return dict(row)

    async def processed_event_count(self) -> int:
        async with self.runtime.transaction() as session:
            count = await session.scalar(
                text(
                    "SELECT count(*) FROM trialscribe.processed_events "
                    "WHERE consumer_group = :group"
                ),
                {"group": self.settings.consumer_group},
            )
        return int(count or 0)


async def with_backbone(scenario: Any, **overrides: Any) -> Any:
    backbone = Backbone(run_identifier(), **overrides)
    await backbone.open()
    try:
        tenant = await seed_tenant(backbone.runtime)
        return await scenario(backbone, tenant)
    finally:
        await backbone.close()


async def a_requested_job_returns_at_once_and_completes_later(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[float, dict[str, Any]]:
    started = asyncio.get_running_loop().time()
    job_id = await backbone.request(tenant, steps=5, step_seconds=0.01)
    elapsed = asyncio.get_running_loop().time() - started

    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    return elapsed, await backbone.job_row(job_id)


def test_a_request_returns_promptly_while_the_worker_finishes_the_job() -> None:
    elapsed, row = asyncio.run(
        with_backbone(a_requested_job_returns_at_once_and_completes_later)
    )

    assert elapsed < 1.0
    assert row["status"] == JobStatus.SUCCEEDED.value
    assert row["progress"] == 100
    assert row["attempt"] == 1
    assert row["error_code"] is None
    assert row["started_at"] is not None
    assert row["finished_at"] is not None


async def the_same_record_delivered_twice_runs_once(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[dict[str, Any], int, int, int]:
    job_id = await backbone.request(tenant, steps=2, step_seconds=0)
    records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)

    deliveries = records + records
    for record in deliveries:
        await backbone.consumer.process(record)
    await backbone.consumer._consumer.commit()

    return (
        await backbone.job_row(job_id),
        await backbone.processed_event_count(),
        len(backbone.handled),
        len(deliveries),
    )


def test_a_duplicated_delivery_never_even_reaches_the_job() -> None:
    row, processed_rows, handled, deliveries = asyncio.run(
        with_backbone(the_same_record_delivered_twice_runs_once)
    )

    assert deliveries == 2
    assert handled == 1
    assert processed_rows == 1
    assert row["status"] == JobStatus.SUCCEEDED.value
    assert row["attempt"] == 1


async def a_job_that_fails_once_succeeds_on_its_retry(
    backbone: Backbone,
    tenant: Tenant,
) -> dict[str, Any]:
    job_id = await backbone.request(
        tenant,
        steps=2,
        step_seconds=0,
        fail_attempts=1,
    )
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    return await backbone.job_row(job_id)


def test_a_failed_first_attempt_is_retried_into_a_single_success() -> None:
    row = asyncio.run(with_backbone(a_job_that_fails_once_succeeds_on_its_retry))

    assert row["status"] == JobStatus.SUCCEEDED.value
    assert row["attempt"] == 2
    assert row["progress"] == 100


async def a_job_that_never_stops_failing_is_recorded_failed(
    backbone: Backbone,
    tenant: Tenant,
) -> dict[str, Any]:
    job_id = await backbone.request(
        tenant,
        steps=2,
        step_seconds=0,
        fail_attempts=MAX_ATTEMPTS,
    )
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    return await backbone.job_row(job_id)


def test_a_job_that_exhausts_its_attempts_ends_failed_on_its_own_ticket() -> None:
    row = asyncio.run(with_backbone(a_job_that_never_stops_failing_is_recorded_failed))

    assert row["status"] == JobStatus.FAILED.value
    assert row["error_code"] == "handler_failed"
    assert row["attempt"] == MAX_ATTEMPTS
    assert row["finished_at"] is not None


async def a_running_job_stops_when_asked(
    backbone: Backbone,
    tenant: Tenant,
) -> dict[str, Any]:
    job_id = await backbone.request(tenant, steps=40, step_seconds=0.05)
    records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)

    handling = asyncio.create_task(backbone.consumer.process(records[0]))
    await asyncio.sleep(0.3)
    async with backbone.runtime.transaction() as session:
        await backbone._service(session).cancel_job(
            tenant.organization_id,
            job_id,
            datetime.now(UTC),
        )
    await handling

    return await backbone.job_row(job_id)


def test_a_running_job_that_is_cancelled_stops_before_it_finishes() -> None:
    row = asyncio.run(with_backbone(a_running_job_stops_when_asked))

    assert row["status"] == JobStatus.CANCELLED.value
    assert row["error_code"] == "cancelled"
    assert row["progress"] < 100
    assert row["finished_at"] is not None


async def an_interrupted_worker_leaves_the_record_to_be_redelivered(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[dict[str, Any], int]:
    """Handle a record, never commit its offset, then hand it back again.

    That is exactly what a worker crash looks like from the broker's side, so a
    correct runtime must end with one outcome and one receipt either way.
    """

    job_id = await backbone.request(tenant, steps=2, step_seconds=0)
    records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)

    await backbone.consumer.process(records[0])
    await backbone.consumer.process(records[0])
    await backbone.consumer._consumer.commit()

    return await backbone.job_row(job_id), await backbone.processed_event_count()


def test_a_redelivery_after_an_uncommitted_offset_leaves_one_outcome() -> None:
    row, processed_rows = asyncio.run(
        with_backbone(an_interrupted_worker_leaves_the_record_to_be_redelivered)
    )

    assert row["status"] == JobStatus.SUCCEEDED.value
    assert row["attempt"] == 1
    assert processed_rows == 1


async def a_request_for_a_cancelled_job_changes_nothing(
    backbone: Backbone,
    tenant: Tenant,
) -> dict[str, Any]:
    job_id = await backbone.request(tenant, steps=2, step_seconds=0)
    async with backbone.runtime.transaction() as session:
        await backbone._service(session).cancel_job(
            tenant.organization_id,
            job_id,
            datetime.now(UTC),
        )

    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    return await backbone.job_row(job_id)


def test_a_job_cancelled_before_it_started_is_never_run() -> None:
    row = asyncio.run(with_backbone(a_request_for_a_cancelled_job_changes_nothing))

    assert row["status"] == JobStatus.CANCELLED.value
    assert row["attempt"] == 0
    assert row["progress"] == 0
    assert row["started_at"] is None


async def progress_is_sampled_while_the_job_actually_runs(
    backbone: Backbone,
    tenant: Tenant,
) -> list[int]:
    """Watch the number a caller would see, through the real read path.

    Progress is assembled from two sources that can each be stale — the live
    Redis value and the durable watermark — so the only honest check is to read
    it the way the API does, repeatedly, while a job is genuinely running.
    """

    job_id = await backbone.request(tenant, steps=8, step_seconds=0.05)
    records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)
    handling = asyncio.create_task(backbone.consumer.process(records[0]))

    samples: list[int] = []
    while not handling.done():
        async with backbone.runtime.transaction() as session:
            samples.append(
                (
                    await backbone._service(session).get_job(
                        tenant.organization_id, job_id
                    )
                ).progress
            )
        await asyncio.sleep(0.02)
    await handling

    async with backbone.runtime.transaction() as session:
        samples.append(
            (
                await backbone._service(session).get_job(
                    tenant.organization_id, job_id
                )
            ).progress
        )
    return samples


def test_progress_reported_to_a_caller_never_goes_backwards() -> None:
    samples = asyncio.run(with_backbone(progress_is_sampled_while_the_job_actually_runs))

    assert samples == sorted(samples)
    assert samples[0] == 0
    assert samples[-1] == 100
    assert max(samples[:-1]) > 0


async def a_ticket_is_durable_before_its_event_can_be_seen(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[str, int, int, dict[str, Any]]:
    """Prove the queue message cannot outrun the ticket that justifies it.

    Publishing from the request let a worker be handed a job whose row had not
    committed, give up after its retries, and discard the record — leaving a
    ticket accepted but unrunnable (bug B29). Storing the message beside the
    ticket makes that ordering impossible: nothing is on the topic until the
    relay sweeps, and by then the ticket is committed.
    """

    job_id = await backbone.request(tenant, hand_over=False, steps=2, step_seconds=0)

    status_before = (await backbone.job_row(job_id))["status"]
    on_topic_before = len(await backbone.records(1, 2.0))

    published = (await backbone.relay.drain_once()).published
    settled = await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)

    return status_before, on_topic_before, published + settled, await backbone.job_row(job_id)


def test_no_event_exists_until_its_ticket_is_committed() -> None:
    status_before, on_topic_before, moved, row = asyncio.run(
        with_backbone(a_ticket_is_durable_before_its_event_can_be_seen)
    )

    assert status_before == JobStatus.QUEUED.value
    assert on_topic_before == 0
    assert moved == 2
    assert row["status"] == JobStatus.SUCCEEDED.value
    assert row["attempt"] == 1


async def an_undelivered_event_is_kept_until_the_broker_takes_it(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[int, int, dict[str, Any]]:
    """A relay that cannot reach the broker must not lose the job."""

    job_id = await backbone.request(tenant, hand_over=False, steps=2, step_seconds=0)

    broken = OutboxRelay(backbone.runtime, _RefusingPublisher(), 100, 0.05)
    first = (await broken.drain_once()).failed
    second = (await backbone.relay.drain_once()).published
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)

    return first, second, await backbone.job_row(job_id)


class _RefusingPublisher:
    """A broker that is simply not there."""

    async def publish_raw(self, *arguments: Any, **keywords: Any) -> None:
        raise ConnectionError("broker unreachable do-not-print")


def test_a_broker_outage_delays_a_job_rather_than_losing_it() -> None:
    failed, published, row = asyncio.run(
        with_backbone(an_undelivered_event_is_kept_until_the_broker_takes_it)
    )

    assert failed == 1
    assert published == 1
    assert row["status"] == JobStatus.SUCCEEDED.value
