"""Build the configured chat and embedding providers. Nothing else does."""

from openai import AsyncOpenAI
from fastembed import TextEmbedding

from trialscribe_worker.config import WorkerSecretSettings, WorkerSettings
from trialscribe_worker.providers.deepseek import DeepSeekChatProvider
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider, FakeFault
from trialscribe_worker.providers.fastembed import FastEmbedProvider
from trialscribe_worker.providers.types import ChatProvider, EmbeddingProvider
from trialscribe_worker.utils.enum import ProviderName, ProviderOutcome
from trialscribe_worker.utils.exceptions import ProviderConfigError


def build_providers(
    settings: WorkerSettings,
    secrets: WorkerSecretSettings,
) -> tuple[ChatProvider, EmbeddingProvider]:
    """Return the chat and embedding backends named in settings."""

    return (
        _build_chat(settings, secrets),
        _build_embed(settings),
    )


def _fake_chat_fault(settings: WorkerSettings) -> FakeFault:
    """Read the fault a stress campaign asked the fake chat provider to inject.

    Empty (the default) means no fault: every call behaves exactly like the
    deterministic fake. A campaign sets these three WORKER_FAKE_CHAT_FAULT_*
    variables to make retries, circuit breaking, and partial failure paths
    observable without ever reaching a real provider.
    """

    if not settings.fake_chat_fault_error:
        return FakeFault()
    return FakeFault(
        delay_seconds=settings.fake_chat_fault_delay_seconds,
        error=ProviderOutcome(settings.fake_chat_fault_error),
        fail_times=settings.fake_chat_fault_fail_times,
    )


def _build_chat(
    settings: WorkerSettings,
    secrets: WorkerSecretSettings,
) -> ChatProvider:
    name = settings.chat_provider
    if name == ProviderName.FAKE.value:
        return FakeChatProvider(fault=_fake_chat_fault(settings))
    if name == ProviderName.DEEPSEEK.value:
        if not secrets.api_key():
            raise ProviderConfigError
        client = AsyncOpenAI(
            api_key=secrets.api_key(),
            base_url=secrets.deepseek_base_url,
        )
        return DeepSeekChatProvider(client, settings.chat_model)
    raise ProviderConfigError


def _build_embed(settings: WorkerSettings) -> EmbeddingProvider:
    name = settings.embedding_provider
    if name == ProviderName.FAKE.value:
        return FakeEmbeddingProvider()
    if name == ProviderName.FASTEMBED.value:
        embedder = TextEmbedding(model_name=settings.embedding_model)
        return FastEmbedProvider(
            embedder,
            settings.embedding_model,
            settings.embedding_dimensions,
        )
    raise ProviderConfigError
