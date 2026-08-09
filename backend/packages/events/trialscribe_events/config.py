"""Environment-backed Kafka event backbone configuration."""

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EventBusSettings(BaseSettings):
    """Validated settings shared by event publishers and consumers."""

    model_config = SettingsConfigDict(
        env_prefix="EVENTS_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    bootstrap_servers: str
    topic_prefix: str = Field(default="trialscribe", min_length=1)
    client_id: str = Field(default="trialscribe", min_length=1)
    consumer_group: str = Field(default="trialscribe", min_length=1)
    topic_partitions: int = Field(default=3, ge=1)
    topic_replication_factor: int = Field(default=1, ge=1)
    max_delivery_attempts: int = Field(default=3, ge=1)
    retry_backoff_seconds: float = Field(default=0.5, gt=0)
    retry_backoff_cap_seconds: float = Field(default=8.0, gt=0)
    request_timeout_seconds: float = Field(default=10.0, gt=0)

    @field_validator("bootstrap_servers", mode="before")
    @classmethod
    def validate_bootstrap_servers(cls, value: Any) -> str:
        raw_value = str(value or "").strip()
        entries = [entry.strip() for entry in raw_value.split(",") if entry.strip()]
        if not entries:
            raise ValueError("EVENTS_BOOTSTRAP_SERVERS must be a comma-separated host:port list")
        for entry in entries:
            host, separator, port = entry.rpartition(":")
            if not host or not separator or not port.isdigit():
                raise ValueError(
                    "EVENTS_BOOTSTRAP_SERVERS must be a comma-separated host:port list"
                )
        return ",".join(entries)

    def request_timeout_ms(self) -> int:
        """Return the broker request timeout in the milliseconds aiokafka expects."""

        return int(self.request_timeout_seconds * 1000)
