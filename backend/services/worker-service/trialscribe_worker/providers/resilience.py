"""Timeouts, retries, concurrency limits, and the circuit breaker.

Every provider call goes through these policies. An unbounded external call is
a defect; this module is how the gateway refuses to make one.
"""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from time import monotonic
from typing import TypeVar

from trialscribe_worker.utils.exceptions import (
    ProviderCircuitOpenError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

T = TypeVar("T")

RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ProviderTimeoutError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)


class CircuitState(StrEnum):
    """Whether calls are allowed through to a provider."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Fail closed after a streak of retryable errors, then probe once."""

    def __init__(
        self,
        name: str,
        failure_threshold: int,
        open_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._open_seconds = open_seconds
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        """Return the current breaker state, flipping open to half-open when due."""

        if (
            self._state is CircuitState.OPEN
            and self._clock() - self._opened_at >= self._open_seconds
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def guard(self) -> None:
        """Raise if the breaker is open so the provider is not called."""

        if self.state is CircuitState.OPEN:
            raise ProviderCircuitOpenError

    def record_success(self) -> None:
        """Close the breaker and clear the failure streak."""

        self._state = CircuitState.CLOSED
        self._failures = 0

    def record_failure(self, error: BaseException) -> None:
        """Count a retryable failure; open once the threshold is reached."""

        if not isinstance(error, RETRYABLE_ERRORS):
            return
        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._failures = 0


async def retry_call(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base: float,
    max_backoff: float,
    sleep: Callable[[float], Awaitable[None]],
    rng: Callable[[], float],
) -> T:
    """Run `operation` up to `attempts` times with full-jitter backoff."""

    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except RETRYABLE_ERRORS as error:
            last_error = error
            if attempt >= attempts - 1:
                raise
            delay = min(max_backoff, base * (2**attempt)) * rng()
            if delay > 0:
                await sleep(delay)
        except Exception:
            raise
    assert last_error is not None
    raise last_error
