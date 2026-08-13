from uuid import UUID

import pytest

from trialscribe_worker.config import WorkerSecretSettings, WorkerSettings
from trialscribe_worker.providers.model_catalog import cost_micros
from trialscribe_worker.utils.constant import (
    DEFAULT_CHAT_PROVIDER,
    DEFAULT_CHROMA_URL,
    DEFAULT_DEEPSEEK_BASE_URL,
    PRICING_VERSION_DEFAULT,
)
from trialscribe_worker.utils.exceptions import ProviderConfigError


def test_fake_chat_probe_tokens_cost_two_micros() -> None:
    assert cost_micros("fake-chat", PRICING_VERSION_DEFAULT, 10, 5) == 2


def test_flash_catalog_rates_are_integer_micros() -> None:
    assert cost_micros("deepseek-v4-flash", PRICING_VERSION_DEFAULT, 1000, 500) == 280


def test_unknown_model_is_a_config_error() -> None:
    try:
        cost_micros("not-a-model", PRICING_VERSION_DEFAULT, 1, 1)
    except ProviderConfigError:
        return
    raise AssertionError("unknown model must raise ProviderConfigError")


def test_unknown_pricing_version_is_a_config_error() -> None:
    try:
        cost_micros("fake-chat", "1999-01-01", 10, 5)
    except ProviderConfigError:
        return
    raise AssertionError("unknown version must raise ProviderConfigError")


def test_settings_read_provider_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_CHAT_PROVIDER", "deepseek")
    monkeypatch.setenv("WORKER_EMBEDDING_PROVIDER", "fastembed")
    monkeypatch.setenv("WORKER_PRICING_VERSION", "2026-08-13")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("CHROMA_URL", "http://127.0.0.1:9001")

    settings = WorkerSettings()
    secrets = WorkerSecretSettings()

    assert settings.chat_provider == "deepseek"
    assert settings.embedding_provider == "fastembed"
    assert settings.pricing_version == PRICING_VERSION_DEFAULT
    assert secrets.api_key() == "secret-key"
    assert "secret-key" not in repr(secrets)
    assert secrets.deepseek_base_url == "https://example.invalid"
    assert secrets.chroma_endpoint() == "http://127.0.0.1:9001"


def test_settings_default_to_fake_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "WORKER_CHAT_PROVIDER",
        "WORKER_EMBEDDING_DIMENSIONS",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_API_KEY",
        "CHROMA_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = WorkerSettings()
    secrets = WorkerSecretSettings()

    assert settings.chat_provider == DEFAULT_CHAT_PROVIDER
    assert settings.embedding_dimensions == 384
    assert secrets.deepseek_base_url == DEFAULT_DEEPSEEK_BASE_URL
    assert secrets.chroma_endpoint() == DEFAULT_CHROMA_URL
    assert secrets.api_key() == ""


def test_chat_request_rejects_an_empty_idempotency_key() -> None:
    from pydantic import ValidationError

    from trialscribe_worker.providers.types import ChatRequest

    try:
        ChatRequest(
            messages=[],
            model="fake-chat",
            organization_id=UUID("00000000-0000-4000-8000-000000000001"),
            conversation_id=None,
            job_id=None,
            account_id=None,
            idempotency_key="",
        )
    except ValidationError:
        return
    raise AssertionError("empty idempotency key must be rejected")
