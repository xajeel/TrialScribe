"""The worker process entry point: read job requests and run them."""

import asyncio
import signal
from contextlib import suppress
from urllib.parse import urlparse

import chromadb
from redis.asyncio import Redis

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.consumer import EventConsumer
from trialscribe_events.contracts.job import register_job_events
from trialscribe_events.outbox_relay import OutboxRelay
from trialscribe_events.publisher import create_event_publisher
from trialscribe_events.registry import EventRegistry
from trialscribe_events.topics import ensure_topics
from trialscribe_events.utils.constant import (
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
)

from trialscribe_worker.config import WorkerRedisSettings, WorkerSecretSettings, WorkerSettings
from trialscribe_worker.pipelines.probe import probe_pipeline
from trialscribe_worker.pipelines.provider_probe import provider_probe_pipeline
from trialscribe_worker.providers.factory import build_providers
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.provider_calls import PostgresUsageRecorder
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.runtime.supervisor import ConsumerSupervisor
from trialscribe_worker.services.job_runner import JobContext, JobRunner
from trialscribe_worker.utils.enum import JobKind, ProviderName


def _chroma_host_port(url: str) -> tuple[str, int, bool]:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port, parsed.scheme == "https"


async def _close_chroma(client: object) -> None:
    stop = getattr(client, "stop", None)
    if callable(stop):
        await stop()


async def run_worker(stop: asyncio.Event) -> None:
    """Own every connection the reader needs, and release them all on the way out."""

    worker_settings = WorkerSettings()
    secrets = WorkerSecretSettings()
    event_settings = EventBusSettings(consumer_group=worker_settings.consumer_group)
    registry = register_job_events(EventRegistry())

    runtime = create_database_runtime(DatabaseSettings())
    redis = Redis.from_url(WorkerRedisSettings().connection_url(), decode_responses=False)
    publisher = create_event_publisher(event_settings, registry)
    chat, embed = build_providers(worker_settings, secrets)
    gateway = ProviderGateway(
        chat,
        embed,
        worker_settings,
        PostgresUsageRecorder(runtime),
        chat_provider_name=worker_settings.chat_provider or ProviderName.FAKE.value,
        embed_provider_name=worker_settings.embedding_provider or ProviderName.FAKE.value,
    )
    host, port, ssl = _chroma_host_port(secrets.chroma_endpoint())
    chroma = await chromadb.AsyncHttpClient(host=host, port=port, ssl=ssl)
    chroma_index = ChromaIndex(chroma, embed_query=None)

    async def run_provider_probe(context: JobContext) -> None:
        context.gateway = gateway
        async with runtime.transaction() as session:
            context.evidence = EvidenceIndex(
                EvidenceChunkRepository(session),
                chroma_index,
            )
            await provider_probe_pipeline(context)

    runner = JobRunner(
        runtime,
        JobProgressStore(redis, worker_settings.progress_ttl_seconds),
        worker_settings,
        event_settings,
        {
            JobKind.PROBE: probe_pipeline,
            JobKind.PROVIDER_PROBE: run_provider_probe,
        },
    )

    def build_consumer() -> EventConsumer:
        consumer = EventConsumer(event_settings, registry, runtime, publisher)
        consumer.register_handler(
            JOB_REQUESTED_EVENT_TYPE,
            JOB_EVENT_VERSION,
            runner.handle,
        )
        return consumer

    relay = OutboxRelay(
        runtime,
        publisher,
        worker_settings.outbox_batch_size,
        worker_settings.outbox_poll_seconds,
    )

    try:
        await publisher.start()
        await ensure_topics(
            event_settings,
            list(registry.topics(event_settings.topic_prefix)),
        )
        # The relay hands stored events to the broker; the supervisor reads them
        # back and runs them. Both end together when the stop event is set.
        await asyncio.gather(
            ConsumerSupervisor(build_consumer, worker_settings).run(stop),
            relay.run(stop),
        )
    finally:
        await _close_chroma(chroma)
        await publisher.stop()
        await redis.aclose()
        await runtime.dispose()


async def _serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for received in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(received, stop.set)
    await run_worker(stop)


def main() -> int:
    """Run the worker until it is asked to stop, then exit cleanly."""

    asyncio.run(_serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
