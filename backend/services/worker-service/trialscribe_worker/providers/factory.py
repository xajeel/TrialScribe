"""Build the configured chat and embedding providers. Nothing else does."""

from openai import AsyncOpenAI
from fastembed import TextEmbedding

from trialscribe_worker.config import WorkerSecretSettings, WorkerSettings
from trialscribe_worker.providers.deepseek import DeepSeekChatProvider
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider
from trialscribe_worker.providers.fastembed import FastEmbedProvider
from trialscribe_worker.providers.types import ChatProvider, EmbeddingProvider
from trialscribe_worker.utils.enum import ProviderName
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


def _build_chat(
    settings: WorkerSettings,
    secrets: WorkerSecretSettings,
) -> ChatProvider:
    name = settings.chat_provider
    if name == ProviderName.FAKE.value:
        return FakeChatProvider()
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
