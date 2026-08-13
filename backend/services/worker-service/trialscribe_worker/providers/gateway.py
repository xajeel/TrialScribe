"""The only door pipelines use to talk to a chat or embedding provider."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol
from uuid import UUID

from trialscribe_events.logs import get_event_logger

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.providers.model_catalog import cost_micros
from trialscribe_worker.providers.resilience import CircuitBreaker, retry_call
from trialscribe_worker.providers.types import (
    ChatProvider,
    ChatRequest,
    ChatResult,
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)
from trialscribe_worker.utils.enum import ProviderName, ProviderOperation, ProviderOutcome
from trialscribe_worker.utils.exceptions import (
    ProviderCircuitOpenError,
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = get_event_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderCallRecord:
    """One metered provider attempt, ready to persist."""

    idempotency_key: str
    organization_id: UUID
    conversation_id: UUID | None
    job_id: UUID | None
    account_id: UUID | None
    provider: str
    operation: str
    model: str
    pricing_version: str
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int
    cost_micros: int
    latency_ms: int
    outcome: str


class UsageRecorder(Protocol):
    """Where the gateway writes and looks up metered attempts."""

    async def find(self, idempotency_key: str) -> ProviderCallRecord | None: ...

    async def record(self, record: ProviderCallRecord) -> None: ...


class MemoryUsageRecorder:
    """In-process recorder used until the database-backed one lands."""

    def __init__(self) -> None:
        self.rows: list[ProviderCallRecord] = []

    async def find(self, idempotency_key: str) -> ProviderCallRecord | None:
        succeeded: ProviderCallRecord | None = None
        latest: ProviderCallRecord | None = None
        for row in self.rows:
            if row.idempotency_key != idempotency_key:
                continue
            latest = row
            if row.outcome == ProviderOutcome.SUCCEEDED.value:
                succeeded = row
        return succeeded if succeeded is not None else latest

    async def record(self, record: ProviderCallRecord) -> None:
        self.rows.append(record)


class ProviderGateway:
    """Apply timeout, retry, concurrency, and circuit breaking to every call."""

    def __init__(
        self,
        chat: ChatProvider,
        embed: EmbeddingProvider,
        settings: WorkerSettings,
        recorder: UsageRecorder,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
        clock: Callable[[], float] = monotonic,
        chat_provider_name: str = ProviderName.FAKE.value,
        embed_provider_name: str = ProviderName.FAKE.value,
    ) -> None:
        self._chat = chat
        self._embed = embed
        self._settings = settings
        self._recorder = recorder
        self._sleep = sleep
        self._rng = rng
        self._clock = clock
        self._chat_provider_name = chat_provider_name
        self._embed_provider_name = embed_provider_name
        self._chat_limiter = asyncio.Semaphore(settings.provider_max_concurrency)
        self._embed_limiter = asyncio.Semaphore(settings.provider_max_concurrency)
        self._chat_breaker = CircuitBreaker(
            chat_provider_name,
            settings.circuit_failure_threshold,
            settings.circuit_open_seconds,
            clock=clock,
        )
        self._embed_breaker = CircuitBreaker(
            embed_provider_name,
            settings.circuit_failure_threshold,
            settings.circuit_open_seconds,
            clock=clock,
        )

    async def complete(self, request: ChatRequest) -> ChatResult:
        """Run one chat completion through the resilience policy."""

        cached = await self._replay_chat(request)
        if cached is not None:
            return cached
        result = await self._execute(
            operation=lambda: self._chat.complete(request),
            breaker=self._chat_breaker,
            limiter=self._chat_limiter,
            request=request,
            operation_name=ProviderOperation.CHAT.value,
            provider_name=self._chat_provider_name,
        )
        if not isinstance(result, ChatResult):
            raise ProviderUnavailableError
        return result

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Run one embedding batch through the resilience policy."""

        cached = await self._replay_embed(request)
        if cached is not None:
            return cached
        result = await self._execute(
            operation=lambda: self._embed.embed(request),
            breaker=self._embed_breaker,
            limiter=self._embed_limiter,
            request=request,
            operation_name=ProviderOperation.EMBED.value,
            provider_name=self._embed_provider_name,
        )
        if not isinstance(result, EmbeddingResult):
            raise ProviderUnavailableError
        return result

    async def _replay_chat(self, request: ChatRequest) -> ChatResult | None:
        row = await self._recorder.find(request.idempotency_key)
        if row is None or row.outcome != ProviderOutcome.SUCCEEDED.value:
            return None
        return ChatResult(
            text="",
            model=row.model,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_hit_tokens=row.cache_hit_tokens,
            latency_ms=row.latency_ms,
        )

    async def _replay_embed(self, request: EmbeddingRequest) -> EmbeddingResult | None:
        row = await self._recorder.find(request.idempotency_key)
        if row is None or row.outcome != ProviderOutcome.SUCCEEDED.value:
            return None
        return EmbeddingResult(
            vectors=[],
            model=row.model,
            dimensions=self._settings.embedding_dimensions,
            input_tokens=row.input_tokens,
            latency_ms=row.latency_ms,
        )

    async def _execute(
        self,
        *,
        operation: Callable[[], Awaitable[ChatResult | EmbeddingResult]],
        breaker: CircuitBreaker,
        limiter: asyncio.Semaphore,
        request: ChatRequest | EmbeddingRequest,
        operation_name: str,
        provider_name: str,
    ) -> ChatResult | EmbeddingResult:
        started = self._clock()

        async def attempt() -> ChatResult | EmbeddingResult:
            breaker.guard()
            async with limiter:
                try:
                    result = await operation()
                except ProviderCircuitOpenError:
                    raise
                except Exception as error:
                    breaker.record_failure(error)
                    await self._meter(
                        request,
                        provider_name,
                        operation_name,
                        request.model,
                        0,
                        0,
                        0,
                        started,
                        _outcome_for(error),
                    )
                    raise
                else:
                    breaker.record_success()
                    input_tokens, output_tokens, cache_hit_tokens = _usage_from(result)
                    await self._meter(
                        request,
                        provider_name,
                        operation_name,
                        result.model,
                        input_tokens,
                        output_tokens,
                        cache_hit_tokens,
                        started,
                        ProviderOutcome.SUCCEEDED,
                    )
                    return result

        try:
            breaker.guard()
            async with asyncio.timeout(self._settings.provider_timeout_seconds):
                return await retry_call(
                    attempt,
                    attempts=self._settings.provider_retry_attempts,
                    base=self._settings.provider_retry_base_seconds,
                    max_backoff=self._settings.provider_retry_max_seconds,
                    sleep=self._sleep,
                    rng=self._rng,
                )
        except TimeoutError as timeout_error:
            timeout = ProviderTimeoutError()
            timeout.__cause__ = timeout_error
            breaker.record_failure(timeout)
            await self._meter(
                request,
                provider_name,
                operation_name,
                request.model,
                0,
                0,
                0,
                started,
                ProviderOutcome.TIMEOUT,
            )
            raise timeout from timeout_error
        except ProviderCircuitOpenError:
            await self._meter(
                request,
                provider_name,
                operation_name,
                request.model,
                0,
                0,
                0,
                started,
                ProviderOutcome.CIRCUIT_OPEN,
            )
            raise

    async def _meter(
        self,
        request: ChatRequest | EmbeddingRequest,
        provider_name: str,
        operation_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int,
        started: float,
        outcome: ProviderOutcome,
    ) -> None:
        record = ProviderCallRecord(
            idempotency_key=request.idempotency_key,
            organization_id=request.organization_id,
            conversation_id=request.conversation_id,
            job_id=request.job_id,
            account_id=request.account_id,
            provider=provider_name,
            operation=operation_name,
            model=model,
            pricing_version=self._settings.pricing_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cost_micros=_safe_cost(
                model,
                self._settings.pricing_version,
                input_tokens,
                output_tokens,
                cache_hit_tokens,
            ),
            latency_ms=max(0, int((self._clock() - started) * 1000)),
            outcome=outcome.value,
        )
        try:
            await self._recorder.record(record)
        except Exception:
            # Metering is optional relative to the provider result: a failed
            # write must not undo a call that already succeeded (B28).
            logger.warning("provider.usage_record_failed")


def _usage_from(result: ChatResult | EmbeddingResult) -> tuple[int, int, int]:
    if isinstance(result, ChatResult):
        return result.input_tokens, result.output_tokens, result.cache_hit_tokens
    return result.input_tokens, 0, 0


def _outcome_for(error: BaseException) -> ProviderOutcome:
    if isinstance(error, ProviderTimeoutError):
        return ProviderOutcome.TIMEOUT
    if isinstance(error, ProviderRateLimitedError):
        return ProviderOutcome.RATE_LIMITED
    if isinstance(error, ProviderCircuitOpenError):
        return ProviderOutcome.CIRCUIT_OPEN
    if isinstance(error, ProviderConfigError):
        return ProviderOutcome.ERROR
    if isinstance(error, ProviderUnavailableError):
        return ProviderOutcome.ERROR
    return ProviderOutcome.ERROR


def _safe_cost(
    model: str,
    version: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int,
) -> int:
    try:
        return cost_micros(
            model,
            version,
            input_tokens,
            output_tokens,
            cache_hit_tokens,
        )
    except ProviderConfigError:
        return 0
