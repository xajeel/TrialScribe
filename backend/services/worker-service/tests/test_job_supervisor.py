import asyncio

import pytest

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.runtime.supervisor import ConsumerSupervisor

BASE_SECONDS = 1.0
CAP_SECONDS = 8.0


class FakeConsumer:
    """A reader that behaves however the test needs it to."""

    def __init__(self, behaviour: str, stop: asyncio.Event) -> None:
        self.behaviour = behaviour
        self.started = False
        self.stopped = False
        self._stop = stop

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def run(self) -> None:
        if self.behaviour == "raises":
            raise RuntimeError("broker unreachable do-not-print")
        if self.behaviour == "returns":
            return
        await self._stop.wait()
        await asyncio.sleep(3600)


def settings(**overrides: float) -> WorkerSettings:
    values: dict[str, float] = {
        "supervisor_restart_seconds": BASE_SECONDS,
        "supervisor_restart_cap_seconds": CAP_SECONDS,
    }
    values.update(overrides)
    return WorkerSettings(**values)  # type: ignore[arg-type]


class Harness:
    """Drive the supervisor without waiting for any real time to pass."""

    def __init__(self, behaviour: str, restarts_before_stop: int) -> None:
        self.behaviour = behaviour
        self.restarts_before_stop = restarts_before_stop
        self.consumers: list[FakeConsumer] = []
        self.delays: list[float] = []
        self.now = 0.0
        self.lifetime = 0.0
        self.stop = asyncio.Event()

    def build(self) -> FakeConsumer:
        consumer = FakeConsumer(self.behaviour, self.stop)
        self.consumers.append(consumer)
        self.now += self.lifetime
        return consumer

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        if len(self.delays) >= self.restarts_before_stop:
            self.stop.set()

    def clock(self) -> float:
        return self.now


async def supervise(harness: Harness, worker_settings: WorkerSettings) -> None:
    supervisor = ConsumerSupervisor(
        harness.build,
        worker_settings,
        sleep=harness.sleep,
        clock=harness.clock,
    )
    await supervisor.run(harness.stop)


def test_a_reader_that_keeps_failing_is_restarted_with_a_doubling_delay() -> None:
    harness = Harness("raises", restarts_before_stop=3)

    asyncio.run(supervise(harness, settings()))

    assert harness.delays == [1.0, 2.0, 4.0]
    assert len(harness.consumers) == 3


def test_the_restart_delay_never_grows_past_its_ceiling() -> None:
    harness = Harness("raises", restarts_before_stop=6)

    asyncio.run(supervise(harness, settings()))

    assert harness.delays == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_a_reader_that_ran_long_enough_resets_the_delay() -> None:
    harness = Harness("raises", restarts_before_stop=3)
    harness.lifetime = CAP_SECONDS

    asyncio.run(supervise(harness, settings()))

    assert harness.delays == [1.0, 1.0, 1.0]


def test_every_restart_closes_the_reader_it_replaced() -> None:
    harness = Harness("raises", restarts_before_stop=3)

    asyncio.run(supervise(harness, settings()))

    assert all(consumer.started for consumer in harness.consumers)
    assert all(consumer.stopped for consumer in harness.consumers)


def test_a_reader_that_simply_returns_is_still_brought_back() -> None:
    harness = Harness("returns", restarts_before_stop=2)

    asyncio.run(supervise(harness, settings()))

    assert harness.delays == [1.0, 2.0]
    assert len(harness.consumers) == 2


def test_a_stop_request_ends_a_reader_that_is_still_waiting_for_records() -> None:
    async def scenario() -> Harness:
        harness = Harness("blocks", restarts_before_stop=1)
        supervisor = ConsumerSupervisor(
            harness.build,
            settings(),
            sleep=harness.sleep,
            clock=harness.clock,
        )
        supervising = asyncio.create_task(supervisor.run(harness.stop))
        await asyncio.sleep(0)
        harness.stop.set()
        await asyncio.wait_for(supervising, timeout=5)
        return harness

    harness = asyncio.run(scenario())

    assert len(harness.consumers) == 1
    assert harness.consumers[0].stopped is True
    assert harness.delays == []


def test_a_supervisor_asked_to_stop_before_it_starts_never_builds_a_reader() -> None:
    async def scenario() -> Harness:
        harness = Harness("blocks", restarts_before_stop=1)
        harness.stop.set()
        supervisor = ConsumerSupervisor(
            harness.build,
            settings(),
            sleep=harness.sleep,
            clock=harness.clock,
        )
        await supervisor.run(harness.stop)
        return harness

    harness = asyncio.run(scenario())

    assert harness.consumers == []


def test_a_restart_ceiling_below_the_base_delay_is_refused() -> None:
    with pytest.raises(ValueError):
        settings(supervisor_restart_seconds=10.0, supervisor_restart_cap_seconds=5.0)
