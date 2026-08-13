import asyncio
from uuid import UUID, uuid4

import pytest

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider, FakeFault
from trialscribe_worker.providers.gateway import MemoryUsageRecorder, ProviderGateway
from trialscribe_worker.providers.types import ChatMessage, ChatRequest, EmbeddingRequest
from trialscribe_worker.utils.enum import ProviderOutcome
from trialscribe_worker.utils.exceptions import (
    ProviderCircuitOpenError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000201")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000202")
JOB_ID = UUID("00000000-0000-4000-8000-000000000203")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000204")


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


async def _no_sleep(_seconds: float) -> None:
    return None


def _settings(**overrides: object) -> WorkerSettings:
    values = {
        "provider_timeout_seconds": 30.0,
        "provider_retry_attempts": 3,
        "provider_retry_base_seconds": 0.01,
        "provider_retry_max_seconds": 0.01,
        "provider_max_concurrency": 8,
        "circuit_failure_threshold": 5,
        "circuit_open_seconds": 30.0,
        "pricing_version": "2026-08-13",
    }
    values.update(overrides)
    return WorkerSettings(**values)


def _chat_request(key: str | None = None) -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role="user", content="ping")],
        model="fake-chat",
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        job_id=JOB_ID,
        account_id=ACCOUNT_ID,
        idempotency_key=key or str(uuid4()),
    )


def _embed_request(key: str | None = None) -> EmbeddingRequest:
    return EmbeddingRequest(
        texts=["one"],
        model="fake-embed",
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        job_id=JOB_ID,
        account_id=ACCOUNT_ID,
        idempotency_key=key or str(uuid4()),
    )


def _gateway(
    chat: FakeChatProvider | None = None,
    embed: FakeEmbeddingProvider | None = None,
    recorder: MemoryUsageRecorder | None = None,
    settings: WorkerSettings | None = None,
    clock: ManualClock | None = None,
) -> tuple[ProviderGateway, FakeChatProvider, FakeEmbeddingProvider, MemoryUsageRecorder]:
    chat_provider = chat or FakeChatProvider()
    embed_provider = embed or FakeEmbeddingProvider()
    usage = recorder or MemoryUsageRecorder()
    gateway = ProviderGateway(
        chat_provider,
        embed_provider,
        settings or _settings(),
        usage,
        sleep=_no_sleep,
        rng=lambda: 0.0,
        clock=clock or ManualClock(),
    )
    return gateway, chat_provider, embed_provider, usage


def test_successful_chat_records_two_micros() -> None:
    gateway, chat, _embed, usage = _gateway()

    result = asyncio.run(gateway.complete(_chat_request()))

    assert result.text == "echo:ping"
    assert chat.calls == 1
    assert len(usage.rows) == 1
    assert usage.rows[0].outcome == ProviderOutcome.SUCCEEDED.value
    assert usage.rows[0].cost_micros == 2
    assert usage.rows[0].input_tokens == 10
    assert usage.rows[0].output_tokens == 5
    assert usage.rows[0].organization_id == ORGANIZATION_ID
    assert usage.rows[0].job_id == JOB_ID


def test_idempotent_replay_does_not_call_the_provider_again() -> None:
    gateway, chat, _embed, _usage = _gateway()
    request = _chat_request("stable-key")

    asyncio.run(gateway.complete(request))
    asyncio.run(gateway.complete(request))

    assert chat.calls == 1


def test_timeout_records_timeout_and_raises() -> None:
    chat = FakeChatProvider(fault=FakeFault(delay_seconds=1.0))
    gateway, _chat, _embed, usage = _gateway(
        chat=chat,
        settings=_settings(provider_timeout_seconds=0.05, provider_retry_attempts=1),
    )

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(gateway.complete(_chat_request()))

    assert usage.rows[-1].outcome == ProviderOutcome.TIMEOUT.value


def test_rate_limited_retries_then_succeeds_and_records_each_attempt() -> None:
    chat = FakeChatProvider(
        fault=FakeFault(error=ProviderOutcome.RATE_LIMITED, fail_times=2),
    )
    gateway, _chat, _embed, usage = _gateway(
        chat=chat,
        settings=_settings(provider_retry_attempts=3),
    )

    result = asyncio.run(gateway.complete(_chat_request()))

    assert result.text == "echo:ping"
    assert chat.calls == 3
    assert len(usage.rows) == 3
    assert [row.outcome for row in usage.rows] == [
        ProviderOutcome.RATE_LIMITED.value,
        ProviderOutcome.RATE_LIMITED.value,
        ProviderOutcome.SUCCEEDED.value,
    ]


def test_exhausted_retries_record_failures_only() -> None:
    chat = FakeChatProvider(
        fault=FakeFault(error=ProviderOutcome.ERROR, fail_times=5),
    )
    gateway, _chat, _embed, usage = _gateway(
        chat=chat,
        settings=_settings(provider_retry_attempts=2),
    )

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(gateway.complete(_chat_request()))

    assert chat.calls == 2
    assert len(usage.rows) == 2
    assert all(row.outcome == ProviderOutcome.ERROR.value for row in usage.rows)


def test_circuit_opens_then_rejects_without_calling_the_provider() -> None:
    chat = FakeChatProvider(
        fault=FakeFault(error=ProviderOutcome.ERROR, fail_times=0),
    )
    gateway, _chat, _embed, _usage = _gateway(
        chat=chat,
        settings=_settings(
            provider_retry_attempts=1,
            circuit_failure_threshold=5,
        ),
    )
    for _ in range(5):
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(gateway.complete(_chat_request()))
    calls_after_open = chat.calls
    with pytest.raises(ProviderCircuitOpenError):
        asyncio.run(gateway.complete(_chat_request()))
    assert chat.calls == calls_after_open


def test_circuit_closes_after_open_seconds_on_success() -> None:
    clock = ManualClock()
    chat = FakeChatProvider(
        fault=FakeFault(error=ProviderOutcome.ERROR, fail_times=5),
    )
    gateway, _chat, _embed, _usage = _gateway(
        chat=chat,
        settings=_settings(
            provider_retry_attempts=1,
            circuit_failure_threshold=5,
            circuit_open_seconds=10.0,
        ),
        clock=clock,
    )
    for _ in range(5):
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(gateway.complete(_chat_request()))
    clock.advance(10.0)
    result = asyncio.run(gateway.complete(_chat_request()))
    assert result.text == "echo:ping"


def test_semaphore_caps_in_flight_embeds() -> None:
    embed = FakeEmbeddingProvider(fault=FakeFault(delay_seconds=0.05))
    gateway, _chat, _embed, _usage = _gateway(
        embed=embed,
        settings=_settings(provider_max_concurrency=1, provider_timeout_seconds=2.0),
    )

    async def both() -> None:
        await asyncio.gather(
            gateway.embed(_embed_request()),
            gateway.embed(_embed_request()),
        )

    asyncio.run(both())
    assert embed.peak_in_flight == 1


def test_usage_record_failure_does_not_hide_success() -> None:
    class BoomRecorder(MemoryUsageRecorder):
        async def record(self, record: object) -> None:
            raise RuntimeError("disk full")

    recorder = BoomRecorder()
    gateway, _chat, _embed, _usage = _gateway(recorder=recorder)

    result = asyncio.run(gateway.complete(_chat_request()))
    assert result.text == "echo:ping"
