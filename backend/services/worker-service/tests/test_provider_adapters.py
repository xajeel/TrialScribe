import asyncio
import threading
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import openai
import pytest
from pydantic import SecretStr

from trialscribe_worker.config import WorkerSecretSettings, WorkerSettings
from trialscribe_worker.providers.deepseek import DeepSeekChatProvider
from trialscribe_worker.providers.factory import build_providers
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider
from trialscribe_worker.providers.fastembed import FastEmbedProvider
from trialscribe_worker.providers.types import ChatMessage, ChatRequest, EmbeddingRequest
from trialscribe_worker.utils.exceptions import (
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000301")


def _chat_request() -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="deepseek-v4-flash",
        organization_id=ORGANIZATION_ID,
        conversation_id=None,
        job_id=None,
        account_id=None,
        idempotency_key=str(uuid4()),
    )


def _embed_request() -> EmbeddingRequest:
    return EmbeddingRequest(
        texts=["alpha"],
        model="BAAI/bge-small-en-v1.5",
        organization_id=ORGANIZATION_ID,
        conversation_id=None,
        job_id=None,
        account_id=None,
        idempotency_key=str(uuid4()),
    )


class RecordingCompletions:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, object] = {}

    async def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class RecordingClient:
    def __init__(self, completions: RecordingCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def _completion(
    *,
    text: str = "ok",
    prompt_tokens: int = 4,
    completion_tokens: int = 6,
    cached_tokens: int = 2,
    choices: list[object] | None = None,
) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
    )
    if choices is None:
        choices = [SimpleNamespace(message=SimpleNamespace(content=text))]
    return SimpleNamespace(choices=choices, usage=usage)


def test_deepseek_maps_usage_including_cache_hits() -> None:
    completions = RecordingCompletions(response=_completion())
    provider = DeepSeekChatProvider(RecordingClient(completions), "deepseek-v4-flash")

    result = asyncio.run(provider.complete(_chat_request()))

    assert result.text == "ok"
    assert result.input_tokens == 4
    assert result.output_tokens == 6
    assert result.cache_hit_tokens == 2
    assert completions.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_empty_choices_are_unavailable() -> None:
    completions = RecordingCompletions(response=_completion(choices=[]))
    provider = DeepSeekChatProvider(RecordingClient(completions), "deepseek-v4-flash")
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.complete(_chat_request()))


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (openai.APITimeoutError(request=None), ProviderTimeoutError),
        (httpx.TimeoutException("slow"), ProviderTimeoutError),
        (
            openai.RateLimitError(
                message="slow down",
                response=httpx.Response(429, request=httpx.Request("POST", "https://example.invalid")),
                body=None,
            ),
            ProviderRateLimitedError,
        ),
        (
            openai.InternalServerError(
                message="down",
                response=httpx.Response(503, request=httpx.Request("POST", "https://example.invalid")),
                body=None,
            ),
            ProviderUnavailableError,
        ),
        (
            openai.APIStatusError(
                message="bad",
                response=httpx.Response(400, request=httpx.Request("POST", "https://example.invalid")),
                body=None,
            ),
            ProviderConfigError,
        ),
    ],
)
def test_deepseek_maps_http_classes(error: Exception, expected: type[Exception]) -> None:
    completions = RecordingCompletions(error=error)
    provider = DeepSeekChatProvider(RecordingClient(completions), "deepseek-v4-flash")
    with pytest.raises(expected):
        asyncio.run(provider.complete(_chat_request()))


class ThreadRecordingEmbedder:
    def __init__(self, width: int = 384) -> None:
        self.width = width
        self.thread_id: int | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.thread_id = threading.get_ident()
        return [[0.1] * self.width for _ in texts]


def test_fastembed_runs_off_the_event_loop() -> None:
    embedder = ThreadRecordingEmbedder()
    provider = FastEmbedProvider(embedder, "BAAI/bge-small-en-v1.5", 384)
    main_thread = threading.get_ident()

    result = asyncio.run(provider.embed(_embed_request()))

    assert result.dimensions == 384
    assert result.vectors == [[0.1] * 384]
    assert embedder.thread_id is not None
    assert embedder.thread_id != main_thread


def test_fastembed_rejects_the_wrong_dimension() -> None:
    provider = FastEmbedProvider(ThreadRecordingEmbedder(width=10), "BAAI/bge-small-en-v1.5", 384)
    with pytest.raises(ProviderConfigError):
        asyncio.run(provider.embed(_embed_request()))


def test_factory_returns_fakes_for_default_settings() -> None:
    chat, embed = build_providers(
        WorkerSettings(chat_provider="fake", embedding_provider="fake"),
        WorkerSecretSettings(),
    )
    assert isinstance(chat, FakeChatProvider)
    assert isinstance(embed, FakeEmbeddingProvider)


def test_factory_rejects_deepseek_without_a_key() -> None:
    with pytest.raises(ProviderConfigError):
        build_providers(
            WorkerSettings(chat_provider="deepseek", embedding_provider="fake"),
            WorkerSecretSettings(deepseek_api_key=SecretStr("")),
        )


def test_factory_rejects_an_unknown_provider() -> None:
    with pytest.raises(ProviderConfigError):
        build_providers(
            WorkerSettings(chat_provider="unknown", embedding_provider="fake"),
            WorkerSecretSettings(),
        )
