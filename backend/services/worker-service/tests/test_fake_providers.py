from time import monotonic
from uuid import UUID, uuid4
import asyncio

import pytest

from trialscribe_worker.providers.fake import (
    FAKE_CHAT_INPUT_TOKENS,
    FAKE_CHAT_OUTPUT_TOKENS,
    FakeChatProvider,
    FakeEmbeddingProvider,
    FakeFault,
    fake_vector_for,
)
from trialscribe_worker.providers.types import (
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
)
from trialscribe_worker.utils.constant import DEFAULT_EMBEDDING_DIMENSIONS
from trialscribe_worker.utils.enum import ProviderOutcome
from trialscribe_worker.utils.exceptions import (
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000101")


def _chat_request(text: str = "hello") -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role="user", content=text)],
        model="fake-chat",
        organization_id=ORGANIZATION_ID,
        conversation_id=None,
        job_id=None,
        account_id=None,
        idempotency_key=str(uuid4()),
    )


def _embed_request(texts: list[str] | None = None) -> EmbeddingRequest:
    return EmbeddingRequest(
        texts=["alpha", "beta"] if texts is None else texts,
        model="fake-embed",
        organization_id=ORGANIZATION_ID,
        conversation_id=None,
        job_id=None,
        account_id=None,
        idempotency_key=str(uuid4()),
    )


def test_chat_echoes_last_user_message_with_fixed_tokens() -> None:
    result = asyncio.run(FakeChatProvider().complete(_chat_request("hello world")))

    assert result.text == "echo:hello world"
    assert result.model == "fake-chat"
    assert result.input_tokens == FAKE_CHAT_INPUT_TOKENS
    assert result.output_tokens == FAKE_CHAT_OUTPUT_TOKENS
    assert result.cache_hit_tokens == 0
    assert result.latency_ms >= 0


def test_embeddings_are_deterministic_and_384_wide() -> None:
    result = asyncio.run(FakeEmbeddingProvider().embed(_embed_request()))

    assert result.dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert len(result.vectors) == 2
    assert result.vectors[0] == fake_vector_for("alpha")
    assert result.vectors[1] == fake_vector_for("beta")
    assert result.vectors[0] != result.vectors[1]
    assert result.input_tokens == 2
    again = asyncio.run(FakeEmbeddingProvider().embed(_embed_request()))
    assert again.vectors == result.vectors


def test_empty_embedding_batch_is_a_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        asyncio.run(FakeEmbeddingProvider().embed(_embed_request([])))


def test_configured_delay_is_observed() -> None:
    provider = FakeChatProvider(fault=FakeFault(delay_seconds=0.05))
    started = monotonic()
    asyncio.run(provider.complete(_chat_request()))
    assert monotonic() - started >= 0.05


@pytest.mark.parametrize(
    ("outcome", "error_type"),
    [
        (ProviderOutcome.TIMEOUT, ProviderTimeoutError),
        (ProviderOutcome.RATE_LIMITED, ProviderRateLimitedError),
        (ProviderOutcome.ERROR, ProviderUnavailableError),
    ],
)
def test_fault_fails_then_succeeds(
    outcome: ProviderOutcome,
    error_type: type[Exception],
) -> None:
    provider = FakeChatProvider(fault=FakeFault(error=outcome, fail_times=2))
    with pytest.raises(error_type):
        asyncio.run(provider.complete(_chat_request()))
    with pytest.raises(error_type):
        asyncio.run(provider.complete(_chat_request()))
    result = asyncio.run(provider.complete(_chat_request()))
    assert result.text.startswith("echo:")


def test_zero_fail_times_always_raises() -> None:
    provider = FakeChatProvider(
        fault=FakeFault(error=ProviderOutcome.ERROR, fail_times=0),
    )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.complete(_chat_request()))
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.complete(_chat_request()))


def test_embedding_faults_match_chat_faults() -> None:
    provider = FakeEmbeddingProvider(
        fault=FakeFault(error=ProviderOutcome.RATE_LIMITED, fail_times=1),
    )
    with pytest.raises(ProviderRateLimitedError):
        asyncio.run(provider.embed(_embed_request()))
    result = asyncio.run(provider.embed(_embed_request(["only"])))
    assert len(result.vectors[0]) == DEFAULT_EMBEDDING_DIMENSIONS
