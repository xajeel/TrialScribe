"""The worker process entry point: read job requests and run them."""

import asyncio
import signal
from contextlib import suppress

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

from trialscribe_worker.config import WorkerRedisSettings, WorkerSettings
from trialscribe_worker.pipelines.probe import probe_pipeline
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.runtime.supervisor import ConsumerSupervisor
from trialscribe_worker.services.job_runner import JobRunner
from trialscribe_worker.utils.enum import JobKind


async def run_worker(stop: asyncio.Event) -> None:
    """Own every connection the reader needs, and release them all on the way out."""

    worker_settings = WorkerSettings()
    event_settings = EventBusSettings(consumer_group=worker_settings.consumer_group)
    registry = register_job_events(EventRegistry())

    runtime = create_database_runtime(DatabaseSettings())
    redis = Redis.from_url(WorkerRedisSettings().connection_url(), decode_responses=False)
    publisher = create_event_publisher(event_settings, registry)
    runner = JobRunner(
        runtime,
        JobProgressStore(redis, worker_settings.progress_ttl_seconds),
        worker_settings,
        event_settings,
        {JobKind.PROBE: probe_pipeline},
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
