import asyncio
import os
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import chromadb
import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import DatabaseRuntime, create_database_runtime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.consumer import EventConsumer
from trialscribe_events.contracts.job import register_job_events
from trialscribe_events.outbox_relay import OutboxRelay
from trialscribe_events.publisher import EventPublisher, create_event_publisher
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.outbox import OutboxRepository
from trialscribe_events.topics import ensure_topics
from trialscribe_events.utils.constant import (
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
)

from trialscribe_worker.config import WorkerRedisSettings, WorkerSettings
from trialscribe_worker.pipelines.provider_probe import provider_probe_pipeline
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider, FakeFault
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import ChatMessage, ChatRequest
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.repositories.provider_calls import PostgresUsageRecorder
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.services.job_runner import JobContext, JobRunner
from trialscribe_worker.services.jobs import JobService
from trialscribe_worker.utils.constant import DEFAULT_EMBEDDING_DIMENSIONS
from trialscribe_worker.utils.enum import JobKind, JobStatus, ProviderOutcome
from trialscribe_worker.utils.exceptions import (
    JobAttemptFailedError,
    ProviderCircuitOpenError,
    ProviderTimeoutError,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_AI_RUNTIME_INTEGRATION") != "1",
        reason="requires the isolated PostgreSQL, Redis, Kafka, and Chroma test project",
    ),
]

CONSUME_TIMEOUT_SECONDS = 30.0
REPO_ROOT = Path(__file__).resolve().parents[4]


def run_identifier() -> str:
    return uuid.uuid4().hex[:12]


def event_settings(identifier: str, **overrides: Any) -> EventBusSettings:
    values: dict[str, Any] = {
        "bootstrap_servers": os.environ["EVENTS_BOOTSTRAP_SERVERS"],
        "topic_prefix": f"trialscribe-ai-runtime-{identifier}",
        "client_id": f"ai-runtime-it-{identifier}",
        "consumer_group": f"ai-runtime-it-{identifier}",
        "topic_partitions": 1,
        "topic_replication_factor": 1,
        "max_delivery_attempts": 3,
        "retry_backoff_seconds": 0.05,
        "retry_backoff_cap_seconds": 0.2,
    }
    values.update(overrides)
    return EventBusSettings(**values)


class Tenant:
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


async def connect_chroma() -> Any:
    parsed = urlparse(os.environ["CHROMA_URL"])
    deadline = time.monotonic() + 30.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return await chromadb.AsyncHttpClient(
                host=parsed.hostname or "127.0.0.1",
                port=parsed.port or 8000,
                ssl=parsed.scheme == "https",
            )
        except Exception as error:
            last_error = error
            await asyncio.sleep(0.5)
    raise RuntimeError("chroma client could not connect") from last_error


async def close_chroma(client: object) -> None:
    stop = getattr(client, "stop", None)
    if callable(stop):
        await stop()


def compose_command(*arguments: str) -> list[str]:
    command = [
        "docker",
        "compose",
        "--env-file",
        ".env",
        "-p",
        os.environ["COMPOSE_PROJECT_NAME"],
    ]
    for compose_file in os.environ["TRIALSCRIBE_COMPOSE_FILES"].split(","):
        command.extend(("-f", compose_file))
    command.extend(("--profile", "infrastructure", *arguments))
    return command


def published_chroma_url() -> str:
    result = subprocess.run(
        compose_command("port", "chroma", "8000"),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    published = result.stdout.strip()
    if ":" not in published:
        raise RuntimeError("chroma loopback port was not published")
    return f"http://127.0.0.1:{published.rsplit(':', 1)[1]}"


def wait_for_chroma(timeout: float = 120.0) -> None:
    url = os.environ["CHROMA_URL"].rstrip("/") + "/api/v2/heartbeat"
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
        time.sleep(0.5)
    raise RuntimeError(f"chroma did not become healthy: {last_error}")


def restart_chroma() -> None:
    subprocess.run(compose_command("restart", "chroma"), cwd=REPO_ROOT, check=True)
    subprocess.run(
        compose_command("up", "-d", "--wait", "--wait-timeout", "120", "chroma"),
        cwd=REPO_ROOT,
        check=True,
    )
    os.environ["CHROMA_URL"] = published_chroma_url()
    wait_for_chroma()


class Backbone:
    """One isolated AI-runtime scenario: jobs, gateway, and Chroma."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        self.settings = event_settings(identifier)
        self.worker_settings = WorkerSettings(
            progress_persist_step=1,
            chat_provider="fake",
            embedding_provider="fake",
        )
        self.registry = register_job_events(EventRegistry())
        self.runtime: DatabaseRuntime
        self.redis: Redis
        self.publisher: EventPublisher
        self.consumer: EventConsumer
        self.progress: JobProgressStore
        self.chroma: Any
        self.chroma_index: ChromaIndex
        self.gateway: ProviderGateway
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
        self.chroma = await connect_chroma()
        self.chroma_index = ChromaIndex(self.chroma, embed_query=None)
        self.gateway = ProviderGateway(
            FakeChatProvider(),
            FakeEmbeddingProvider(),
            self.worker_settings,
            PostgresUsageRecorder(self.runtime),
            rng=lambda: 0.0,
        )

        async def run_provider_probe(context: JobContext) -> None:
            context.gateway = self.gateway
            async with self.runtime.transaction() as session:
                context.evidence = EvidenceIndex(
                    EvidenceChunkRepository(session),
                    self.chroma_index,
                )
                await provider_probe_pipeline(context)

        runner = JobRunner(
            self.runtime,
            self.progress,
            self.worker_settings,
            self.settings,
            {JobKind.PROVIDER_PROBE: run_provider_probe},
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
        await close_chroma(self.chroma)
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

    async def request_probe(self, tenant: Tenant, *, hand_over: bool = True) -> UUID:
        async with self.runtime.transaction() as session:
            response = await self._service(session).request_job(
                tenant.organization_id,
                tenant.account_id,
                JobCreateRequest(
                    kind=JobKind.PROVIDER_PROBE.value,
                    conversation_id=tenant.conversation_id,
                    parameters={"conversation_id": str(tenant.conversation_id)},
                ),
                datetime.now(UTC),
            )
        if hand_over:
            await self.relay.drain_once()
        return response.id

    async def records(self, expected: int, timeout: float) -> list[Any]:
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
                        "SELECT status, attempt, progress, error_code FROM "
                        "trialscribe.jobs WHERE id = :id"
                    ),
                    {"id": job_id},
                )
            ).mappings().one()
        return dict(row)

    async def provider_calls(self, job_id: UUID) -> list[dict[str, Any]]:
        async with self.runtime.transaction() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT operation, model, input_tokens, output_tokens, "
                        "cost_micros, outcome, idempotency_key, organization_id, "
                        "conversation_id FROM trialscribe.provider_calls "
                        "WHERE job_id = :job_id ORDER BY created_at, id"
                    ),
                    {"job_id": job_id},
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    async def evidence_ids(self, organization_id: UUID, conversation_id: UUID) -> list[UUID]:
        async with self.runtime.transaction() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT id FROM trialscribe.evidence_chunks "
                        "WHERE organization_id = :organization_id "
                        "AND conversation_id = :conversation_id"
                    ),
                    {
                        "organization_id": organization_id,
                        "conversation_id": conversation_id,
                    },
                )
            ).scalars().all()
        return list(rows)


async def with_backbone(scenario: Any) -> Any:
    backbone = Backbone(run_identifier())
    await backbone.open()
    try:
        tenant = await seed_tenant(backbone.runtime)
        return await scenario(backbone, tenant)
    finally:
        await backbone.close()


def _probe_vector() -> list[float]:
    return [0.001] * DEFAULT_EMBEDDING_DIMENSIONS


async def a_provider_probe_is_metered(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[UUID]]:
    job_id = await backbone.request_probe(tenant)
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    return (
        await backbone.job_row(job_id),
        await backbone.provider_calls(job_id),
        await backbone.evidence_ids(tenant.organization_id, tenant.conversation_id),
    )


def test_provider_probe_records_chat_and_embed_costs() -> None:
    row, calls, chunk_ids = asyncio.run(with_backbone(a_provider_probe_is_metered))

    assert row["status"] == JobStatus.SUCCEEDED.value
    assert row["progress"] == 100
    assert chunk_ids
    operations = {call["operation"]: call for call in calls}
    chat = operations["chat"]
    embed = operations["embed"]
    assert chat["cost_micros"] == 2
    assert chat["input_tokens"] == 10
    assert chat["output_tokens"] == 5
    assert chat["outcome"] == "succeeded"
    assert embed["cost_micros"] == 0
    assert embed["outcome"] == "succeeded"


async def a_foreign_organization_sees_no_chunks(
    backbone: Backbone,
    tenant: Tenant,
) -> list[Any]:
    await backbone.request_probe(tenant)
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    stranger = uuid.uuid4()
    async with backbone.runtime.transaction() as session:
        found = await EvidenceIndex(
            EvidenceChunkRepository(session),
            backbone.chroma_index,
        ).search(
            organization_id=stranger,
            conversation_id=tenant.conversation_id,
            vector=_probe_vector(),
            k=5,
        )
    return found


def test_a_second_organization_cannot_read_another_tenants_chunks() -> None:
    found = asyncio.run(with_backbone(a_foreign_organization_sees_no_chunks))
    assert found == []


async def a_chroma_restart_keeps_the_probe_chunk(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[list[UUID], list[UUID]]:
    await backbone.request_probe(tenant)
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    expected = await backbone.evidence_ids(tenant.organization_id, tenant.conversation_id)
    await close_chroma(backbone.chroma)
    restart_chroma()
    backbone.chroma = await connect_chroma()
    backbone.chroma_index = ChromaIndex(backbone.chroma, embed_query=None)
    async with backbone.runtime.transaction() as session:
        found = await EvidenceIndex(
            EvidenceChunkRepository(session),
            backbone.chroma_index,
        ).search(
            organization_id=tenant.organization_id,
            conversation_id=tenant.conversation_id,
            vector=_probe_vector(),
            k=1,
        )
    return [row.id for row in found], expected


def test_chunks_survive_a_chroma_container_restart() -> None:
    found, expected = asyncio.run(with_backbone(a_chroma_restart_keeps_the_probe_chunk))
    assert found
    assert found[0] in expected


async def a_slow_complete_times_out_and_is_metered(runtime: DatabaseRuntime, tenant: Tenant) -> str:
    chat = FakeChatProvider(fault=FakeFault(delay_seconds=2.0))
    gateway = ProviderGateway(
        chat,
        FakeEmbeddingProvider(),
        WorkerSettings(provider_timeout_seconds=0.2, provider_retry_attempts=1),
        PostgresUsageRecorder(runtime),
        rng=lambda: 0.0,
    )
    key = f"timeout-{uuid.uuid4()}"
    try:
        await gateway.complete(
            ChatRequest(
                messages=[ChatMessage(role="user", content="ping")],
                model="fake-chat",
                organization_id=tenant.organization_id,
                conversation_id=tenant.conversation_id,
                job_id=None,
                account_id=tenant.account_id,
                idempotency_key=key,
            )
        )
    except ProviderTimeoutError:
        pass
    else:
        raise AssertionError("slow fake must time out")
    async with runtime.transaction() as session:
        outcome = await session.scalar(
            text(
                "SELECT outcome FROM trialscribe.provider_calls "
                "WHERE idempotency_key = :key"
            ),
            {"key": key},
        )
    return str(outcome)


def test_a_slow_gateway_call_records_timeout() -> None:
    async def scenario() -> str:
        runtime = create_database_runtime(DatabaseSettings())
        try:
            tenant = await seed_tenant(runtime)
            return await a_slow_complete_times_out_and_is_metered(runtime, tenant)
        finally:
            await runtime.dispose()

    assert asyncio.run(scenario()) == "timeout"


async def five_faults_open_the_breaker(runtime: DatabaseRuntime, tenant: Tenant) -> int:
    chat = FakeChatProvider(fault=FakeFault(error=ProviderOutcome.ERROR, fail_times=0))
    gateway = ProviderGateway(
        chat,
        FakeEmbeddingProvider(),
        WorkerSettings(provider_retry_attempts=1, circuit_failure_threshold=5),
        PostgresUsageRecorder(runtime),
        rng=lambda: 0.0,
    )
    for _ in range(5):
        try:
            await gateway.complete(
                ChatRequest(
                    messages=[ChatMessage(role="user", content="ping")],
                    model="fake-chat",
                    organization_id=tenant.organization_id,
                    conversation_id=tenant.conversation_id,
                    job_id=None,
                    account_id=tenant.account_id,
                    idempotency_key=str(uuid.uuid4()),
                )
            )
        except Exception:
            pass
    calls_after_open = chat.calls
    try:
        await gateway.complete(
            ChatRequest(
                messages=[ChatMessage(role="user", content="ping")],
                model="fake-chat",
                organization_id=tenant.organization_id,
                conversation_id=tenant.conversation_id,
                job_id=None,
                account_id=tenant.account_id,
                idempotency_key=str(uuid.uuid4()),
            )
        )
    except ProviderCircuitOpenError:
        pass
    else:
        raise AssertionError("open breaker must reject the next call")
    return chat.calls - calls_after_open


def test_an_open_breaker_does_not_call_the_provider() -> None:
    async def scenario() -> int:
        runtime = create_database_runtime(DatabaseSettings())
        try:
            tenant = await seed_tenant(runtime)
            return await five_faults_open_the_breaker(runtime, tenant)
        finally:
            await runtime.dispose()

    assert asyncio.run(scenario()) == 0


async def a_duplicated_delivery_writes_one_chat_row(
    backbone: Backbone,
    tenant: Tenant,
) -> tuple[int, UUID]:
    job_id = await backbone.request_probe(tenant)
    records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)
    for record in records + records:
        await backbone.consumer.process(record)
    await backbone.consumer._consumer.commit()
    async with backbone.runtime.transaction() as session:
        count = await session.scalar(
            text(
                "SELECT count(*) FROM trialscribe.provider_calls "
                "WHERE idempotency_key = :key AND outcome = 'succeeded'"
            ),
            {"key": f"{job_id}:1:chat:0"},
        )
    return int(count or 0), job_id


def test_duplicate_delivery_leaves_one_succeeded_chat_row() -> None:
    count, _job_id = asyncio.run(with_backbone(a_duplicated_delivery_writes_one_chat_row))
    assert count == 1
