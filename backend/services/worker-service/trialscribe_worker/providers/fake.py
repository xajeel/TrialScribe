"""In-process chat and embedding providers that never leave the process.

Selected by configuration so tests, local runs, and stress campaigns can
exercise timeouts, retries, and faults without a network call or a model file.
"""

import asyncio
from dataclasses import dataclass, field
from time import monotonic

from trialscribe_worker.providers.types import (
    ChatRequest,
    ChatResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from trialscribe_worker.utils.constant import DEFAULT_EMBEDDING_DIMENSIONS
from trialscribe_worker.utils.enum import ProviderOutcome
from trialscribe_worker.utils.exceptions import (
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

FAKE_CHAT_MODEL = "fake-chat"
FAKE_EMBED_MODEL = "fake-embed"
FAKE_CHAT_INPUT_TOKENS = 10
FAKE_CHAT_OUTPUT_TOKENS = 5


@dataclass(slots=True)
class FakeFault:
    """Optional delay and error the fake should inject before answering."""

    delay_seconds: float = 0.0
    error: ProviderOutcome | None = None
    fail_times: int = 0


@dataclass(slots=True)
class _FaultBudget:
    """Count remaining injected failures for one fake instance."""

    fault: FakeFault
    remaining: int = field(init=False)

    def __post_init__(self) -> None:
        self.remaining = self.fault.fail_times

    async def apply(self) -> None:
        """Sleep, then raise while injected failures remain."""

        if self.fault.delay_seconds > 0:
            await asyncio.sleep(self.fault.delay_seconds)
        if self.fault.error is None:
            return
        if self.fault.fail_times == 0 or self.remaining > 0:
            if self.remaining > 0:
                self.remaining -= 1
            raise _exception_for(self.fault.error)


def _exception_for(outcome: ProviderOutcome) -> Exception:
    if outcome is ProviderOutcome.TIMEOUT:
        return ProviderTimeoutError()
    if outcome is ProviderOutcome.RATE_LIMITED:
        return ProviderRateLimitedError()
    return ProviderUnavailableError()


@dataclass(slots=True)
class FakeChatProvider:
    """Echo the last user message, with optional delay and injected faults."""

    fault: FakeFault = field(default_factory=FakeFault)
    calls: int = 0
    _budget: _FaultBudget = field(init=False)

    def __post_init__(self) -> None:
        self._budget = _FaultBudget(self.fault)

    async def complete(self, request: ChatRequest) -> ChatResult:
        """Return a canned completion, or raise the configured fault."""

        started = monotonic()
        self.calls += 1
        await self._budget.apply()
        return ChatResult(
            text=f"echo:{_last_user_content(request)}",
            model=FAKE_CHAT_MODEL,
            input_tokens=FAKE_CHAT_INPUT_TOKENS,
            output_tokens=FAKE_CHAT_OUTPUT_TOKENS,
            cache_hit_tokens=0,
            latency_ms=_elapsed_ms(started),
        )


@dataclass(slots=True)
class FakeEmbeddingProvider:
    """Return a deterministic 384-dimension vector per input text."""

    fault: FakeFault = field(default_factory=FakeFault)
    calls: int = 0
    in_flight: int = 0
    peak_in_flight: int = 0
    _budget: _FaultBudget = field(init=False)

    def __post_init__(self) -> None:
        self._budget = _FaultBudget(self.fault)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Embed each text, or raise the configured fault."""

        started = monotonic()
        self.calls += 1
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            await self._budget.apply()
            if not request.texts:
                raise ProviderConfigError
            return EmbeddingResult(
                vectors=[
                    _deterministic_vector(index)
                    for index, _text in enumerate(request.texts)
                ],
                model=FAKE_EMBED_MODEL,
                dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
                input_tokens=len(request.texts),
                latency_ms=_elapsed_ms(started),
            )
        finally:
            self.in_flight -= 1


def _last_user_content(request: ChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content
    return ""


def _deterministic_vector(index: int) -> list[float]:
    value = min(0.001 * (index + 1), 1.0)
    return [value] * DEFAULT_EMBEDDING_DIMENSIONS


def _elapsed_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000))
