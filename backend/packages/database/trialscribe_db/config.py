"""Environment-backed PostgreSQL configuration."""

from typing import Any

from pydantic import Field, SecretStr, field_validator
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
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0)
    database_pool_recycle_seconds: int = Field(default=1800, ge=-1)

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

    def pool_options(self) -> dict[str, object]:
        """Return the connection-pool shape this process is allowed to use.

        The pool is the real concurrency limit of an asynchronous service: no
        matter how many requests or jobs are in flight, only `pool_size +
        max_overflow` of them can touch PostgreSQL at once. Leaving it at the
        library default hides that limit and makes it impossible to size a
        deployment against `max_connections`. Recycling connections keeps a
        pooler or firewall from handing back a socket the server already closed.
        """

        return {
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
            "pool_timeout": self.database_pool_timeout_seconds,
            "pool_recycle": self.database_pool_recycle_seconds,
        }
