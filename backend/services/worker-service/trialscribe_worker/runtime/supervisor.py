"""Keep the queue reader running, without hammering a broker that is struggling.

The event backbone deliberately ends its reader when a record can neither be
handled nor set aside — that is what keeps an unsettled record uncommitted and
therefore redeliverable (bug B26). Ending is the right behaviour; staying ended
is not. This brings the reader back, waiting a little longer each time until a
ceiling, and resetting once a reader has run long enough to count as healthy.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from trialscribe_events.logs import event_context, get_event_logger

from trialscribe_worker.config import WorkerSettings

logger = get_event_logger(__name__)

ConsumerFactory = Callable[[], Any]
Sleeper = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class ConsumerSupervisor:
    """Run one queue reader at a time, restarting it for as long as asked."""

    def __init__(
        self,
        build_consumer: ConsumerFactory,
        settings: WorkerSettings,
        sleep: Sleeper | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._build_consumer = build_consumer
        self._settings = settings
        self._sleep = sleep or asyncio.sleep
        self._clock = clock or self._loop_time

    async def run(self, stop: asyncio.Event) -> None:
        """Read until asked to stop, restarting after every unplanned exit."""

        delay = self._settings.supervisor_restart_seconds
        while not stop.is_set():
            started = self._clock()
            consumer = self._build_consumer()
            try:
                await self._run_once(consumer, stop)
            except Exception:
                logger.error(
                    "job.consumer_restarting",
                    extra={"event_context": event_context(reason="reader_stopped")},
                )
            finally:
                with suppress(Exception):
                    await consumer.stop()

            if stop.is_set():
                break
            if self._clock() - started >= self._settings.supervisor_restart_cap_seconds:
                delay = self._settings.supervisor_restart_seconds
            await self._sleep(delay)
            delay = min(self._settings.supervisor_restart_cap_seconds, delay * 2)

    async def _run_once(self, consumer: Any, stop: asyncio.Event) -> None:
        """Read records until the reader ends or a stop is requested."""

        await consumer.start()
        reading = asyncio.create_task(consumer.run())
        stopping = asyncio.create_task(stop.wait())
        done, pending = await asyncio.wait(
            {reading, stopping},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if reading in done:
            reading.result()

    @staticmethod
    def _loop_time() -> float:
        return asyncio.get_running_loop().time()
