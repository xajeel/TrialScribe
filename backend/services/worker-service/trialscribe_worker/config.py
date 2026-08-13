"""Environment-backed worker-service configuration."""

from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trialscribe_worker.utils.constant import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_CHAT_PROVIDER,
    DEFAULT_CHROMA_URL,
    DEFAULT_CIRCUIT_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_OPEN_SECONDS,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_PROVIDER_MAX_CONCURRENCY,
    DEFAULT_PROVIDER_RETRY_ATTEMPTS,
    DEFAULT_PROVIDER_RETRY_BASE_SECONDS,
    DEFAULT_PROVIDER_RETRY_MAX_SECONDS,
    DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    MAX_PROGRESS,
    MIN_PROGRESS,
    PRICING_VERSION_DEFAULT,
)


class WorkerSettings(BaseSettings):
    """Validated settings for running and reporting on background jobs."""

    model_config = SettingsConfigDict(
        env_prefix="WORKER_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    consumer_group: str = Field(default="trialscribe-worker", min_length=1)
    progress_ttl_seconds: int = Field(default=86400, gt=0)
    progress_persist_step: int = Field(
        default=10,
        ge=MIN_PROGRESS + 1,
        le=MAX_PROGRESS,
    )
    outbox_poll_seconds: float = Field(default=1.0, gt=0)
    outbox_batch_size: int = Field(default=100, ge=1)
    supervisor_restart_seconds: float = Field(default=1.0, gt=0)
    supervisor_restart_cap_seconds: float = Field(default=30.0, gt=0)
    chat_provider: str = Field(default=DEFAULT_CHAT_PROVIDER, min_length=1)
    embedding_provider: str = Field(default=DEFAULT_EMBEDDING_PROVIDER, min_length=1)
    chat_model: str = Field(default=DEFAULT_CHAT_MODEL, min_length=1)
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, min_length=1)
    embedding_dimensions: int = Field(default=DEFAULT_EMBEDDING_DIMENSIONS, gt=0)
    provider_timeout_seconds: float = Field(
        default=DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        gt=0,
    )
    provider_retry_attempts: int = Field(default=DEFAULT_PROVIDER_RETRY_ATTEMPTS, ge=1)
    provider_retry_base_seconds: float = Field(
        default=DEFAULT_PROVIDER_RETRY_BASE_SECONDS,
        gt=0,
    )
    provider_retry_max_seconds: float = Field(
        default=DEFAULT_PROVIDER_RETRY_MAX_SECONDS,
        gt=0,
    )
    provider_max_concurrency: int = Field(
        default=DEFAULT_PROVIDER_MAX_CONCURRENCY,
        ge=1,
    )
    circuit_failure_threshold: int = Field(
        default=DEFAULT_CIRCUIT_FAILURE_THRESHOLD,
        ge=1,
    )
    circuit_open_seconds: float = Field(default=DEFAULT_CIRCUIT_OPEN_SECONDS, gt=0)
    pricing_version: str = Field(default=PRICING_VERSION_DEFAULT, min_length=1)

    @field_validator("supervisor_restart_cap_seconds")
    @classmethod
    def validate_restart_cap(cls, value: float, info: Any) -> float:
        base = info.data.get("supervisor_restart_seconds")
        if base is not None and value < base:
            raise ValueError(
                "WORKER_SUPERVISOR_RESTART_CAP_SECONDS must not be below the base delay"
            )
        return value


class WorkerRedisSettings(BaseSettings):
    """The shared Redis location, which carries no worker-specific prefix."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    redis_url: SecretStr

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, value: Any) -> SecretStr:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        if not raw_value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL must be a redis://, rediss://, or unix:// URL")
        return SecretStr(raw_value)

    def connection_url(self) -> str:
        """Reveal the URL only for client construction."""

        return self.redis_url.get_secret_value()


class WorkerSecretSettings(BaseSettings):
    """Provider credentials and index location, which carry no WORKER_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    deepseek_api_key: SecretStr = Field(default=SecretStr(""))
    deepseek_base_url: str = Field(default=DEFAULT_DEEPSEEK_BASE_URL, min_length=1)
    chroma_url: str = Field(default=DEFAULT_CHROMA_URL, min_length=1)

    def api_key(self) -> str:
        """Reveal the DeepSeek key only for client construction."""

        return self.deepseek_api_key.get_secret_value()

    def chroma_endpoint(self) -> str:
        """Return the Chroma HTTP origin used to build the async client."""

        return self.chroma_url
