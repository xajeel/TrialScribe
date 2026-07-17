"""Environment-backed PostgreSQL configuration."""

from typing import Any

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSettings(BaseSettings):
    """Validated database settings with redacted credentials."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: Any) -> SecretStr:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        try:
            url = make_url(raw_value)
        except (ArgumentError, TypeError, ValueError):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None

        if url.drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        if not url.host or not url.database:
            raise ValueError("DATABASE_URL must include a host and database name")
        return SecretStr(raw_value)

    def connection_url(self) -> str:
        """Reveal the URL only for database connection construction."""

        return self.database_url.get_secret_value()
