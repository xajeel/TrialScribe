"""Named job, Kafka, and provider metrics with bounded labels."""

from collections.abc import Callable
from typing import TypeVar

from prometheus_client import Counter, Gauge, Histogram

T = TypeVar("T")

JOBS_TOTAL = Counter(
    "trialscribe_jobs_total",
    "Terminal background job outcomes",
    ["kind", "outcome"],
)
JOB_DURATION_SECONDS = Histogram(
    "trialscribe_job_duration_seconds",
    "Seconds from job claim to a terminal outcome",
    ["kind"],
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, float("inf")),
)
EVENTS_CONSUMED_TOTAL = Counter(
    "trialscribe_events_consumed_total",
    "Kafka records settled by a consumer",
    ["event_type", "result"],
)
EVENTS_PUBLISHED_TOTAL = Counter(
    "trialscribe_events_published_total",
    "Kafka produce attempts",
    ["result"],
)
PROVIDER_CALLS_TOTAL = Counter(
    "trialscribe_provider_calls_total",
    "Provider gateway attempts",
    ["provider", "operation", "outcome"],
)
PROVIDER_CIRCUIT_STATE = Gauge(
    "trialscribe_provider_circuit_state",
    "Circuit breaker state (0 closed, 1 half-open, 2 open)",
    ["provider"],
)

CIRCUIT_STATE_VALUES = {
    "closed": 0.0,
    "half_open": 1.0,
    "open": 2.0,
}


def safe_observe(action: Callable[[], T]) -> T | None:
    """Run a metrics write; never let a scoreboard failure undo real work."""

    try:
        return action()
    except Exception:
        return None


def record_job(kind: str, outcome: str, seconds: float) -> None:
    def _record() -> None:
        JOBS_TOTAL.labels(kind=kind, outcome=outcome).inc()
        JOB_DURATION_SECONDS.labels(kind=kind).observe(seconds)

    safe_observe(_record)


def record_event_consumed(event_type: str, result: str) -> None:
    def _record() -> None:
        EVENTS_CONSUMED_TOTAL.labels(event_type=event_type, result=result).inc()

    safe_observe(_record)


def record_event_published(result: str) -> None:
    def _record() -> None:
        EVENTS_PUBLISHED_TOTAL.labels(result=result).inc()

    safe_observe(_record)


def record_provider_call(provider: str, operation: str, outcome: str) -> None:
    def _record() -> None:
        PROVIDER_CALLS_TOTAL.labels(
            provider=provider,
            operation=operation,
            outcome=outcome,
        ).inc()

    safe_observe(_record)


def set_circuit_state(provider: str, state: str) -> None:
    def _record() -> None:
        PROVIDER_CIRCUIT_STATE.labels(provider=provider).set(
            CIRCUIT_STATE_VALUES.get(state, 0.0)
        )

    safe_observe(_record)
