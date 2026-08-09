"""Environment-backed worker-service configuration."""

from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trialscribe_worker.utils.constant import MAX_PROGRESS, MIN_PROGRESS


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
