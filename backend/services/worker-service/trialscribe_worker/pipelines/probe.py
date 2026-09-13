"""A job that does nothing useful, on purpose, and proves the runtime works.

Every real pipeline arrives in a later feature. This one exists so progress,
retry, and cancellation can be exercised end to end today, and it stays useful
afterwards: health checks and load runs need work that costs nothing, behaves the
same every time, and can be told to fail when a failure path needs testing.
"""

import asyncio
from typing import Any

from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    MAX_PROGRESS,
    PROBE_DEFAULT_STEP_SECONDS,
    PROBE_DEFAULT_STEPS,
    PROBE_FAIL_ATTEMPTS_PARAMETER,
    PROBE_MAX_STEP_SECONDS,
    PROBE_MAX_STEPS,
    PROBE_STEP_SECONDS_PARAMETER,
    PROBE_STEPS_PARAMETER,
)
from trialscribe_worker.utils.exceptions import ProbeFaultInjected


def _bounded_int(value: Any, default: int, lowest: int, highest: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(lowest, min(highest, parsed))


def _bounded_float(value: Any, default: float, lowest: float, highest: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(lowest, min(highest, parsed))


async def probe_pipeline(context: JobContext) -> None:
    """Count through a few steps, reporting progress and honouring a stop."""

    steps = _bounded_int(
        context.parameters.get(PROBE_STEPS_PARAMETER),
        PROBE_DEFAULT_STEPS,
        1,
        PROBE_MAX_STEPS,
    )
    step_seconds = _bounded_float(
        context.parameters.get(PROBE_STEP_SECONDS_PARAMETER),
        PROBE_DEFAULT_STEP_SECONDS,
        0.0,
        PROBE_MAX_STEP_SECONDS,
    )
    fail_attempts = _bounded_int(
        context.parameters.get(PROBE_FAIL_ATTEMPTS_PARAMETER),
        0,
        0,
        PROBE_MAX_STEPS,
    )

    if context.attempt <= fail_attempts:
        raise ProbeFaultInjected

    for step in range(1, steps + 1):
        await context.check_cancelled()
        if step_seconds > 0:
            await asyncio.sleep(step_seconds)
        await context.report(round(step / steps * MAX_PROGRESS))
