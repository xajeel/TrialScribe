"""Environment-backed API gateway configuration."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Any, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _decode_public_key(value: Any) -> bytes:
    try:
        decoded = base64.b64decode(str(value), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("AUTH_JWT_PUBLIC_KEY_B64 must be valid base64") from None
    if len(decoded) != 32:
        raise ValueError("AUTH_JWT_PUBLIC_KEY_B64 must encode a 32-byte Ed25519 key")
    return decoded


class GatewaySettings(BaseSettings):
    """Validated routing, browser, token, and timeout settings."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    gateway_auth_service_url: AnyHttpUrl
    gateway_user_service_url: AnyHttpUrl
    gateway_ai_service_url: AnyHttpUrl
    gateway_worker_service_url: AnyHttpUrl
    gateway_cors_origins: Annotated[list[AnyHttpUrl], NoDecode]
    gateway_upstream_connect_timeout_seconds: float
    gateway_upstream_read_timeout_seconds: float
    gateway_upstream_write_timeout_seconds: float
    gateway_upstream_pool_timeout_seconds: float
    auth_jwt_public_key_b64: str
    auth_jwt_issuer: str
    auth_jwt_audience: str

    @field_validator("gateway_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        entries = value.strip()
        if entries.startswith("[") and entries.endswith("]"):
            entries = entries[1:-1]
        return [
            entry.strip().strip("\"'")
            for entry in entries.split(",")
            if entry.strip()
        ]

    @field_validator("auth_jwt_public_key_b64")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _decode_public_key(value)
        return value

    @field_validator("auth_jwt_issuer", "auth_jwt_audience")
    @classmethod
    def validate_token_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("token issuer and audience must not be empty")
        return value

    @field_validator(
        "gateway_upstream_connect_timeout_seconds",
        "gateway_upstream_read_timeout_seconds",
        "gateway_upstream_write_timeout_seconds",
        "gateway_upstream_pool_timeout_seconds",
    )
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("gateway upstream timeouts must be positive")
        return value

    @model_validator(mode="after")
    def validate_service_urls(self) -> Self:
        for field_name in (
            "gateway_auth_service_url",
            "gateway_user_service_url",
            "gateway_ai_service_url",
            "gateway_worker_service_url",
        ):
            service_url = getattr(self, field_name)
            if (
                service_url.path not in {"", "/"}
                or service_url.query
                or service_url.fragment
                or service_url.username
                or service_url.password
            ):
                raise ValueError(
                    "gateway service URLs must be origins without credentials or paths"
                )
        return self

    @model_validator(mode="after")
    def validate_origins(self) -> Self:
        normalized: set[str] = set()
        for origin in self.gateway_cors_origins:
            if origin.path not in {"", "/"} or origin.query or origin.fragment:
                raise ValueError("gateway CORS entries must be origins without paths")
            normalized.add(f"{origin.scheme}://{origin.host}:{origin.port}")
        if not normalized or len(normalized) != len(self.gateway_cors_origins):
            raise ValueError("gateway CORS origins must be non-empty and unique")
        return self

    def verification_key(self) -> Ed25519PublicKey:
        """Build the public-only key used to verify access tokens."""

        return Ed25519PublicKey.from_public_bytes(
            _decode_public_key(self.auth_jwt_public_key_b64)
        )

    def cors_origins(self) -> list[str]:
        """Return normalized browser origins without URL paths."""

        return [str(origin).rstrip("/") for origin in self.gateway_cors_origins]

    def service_url(self, service: str) -> str:
        """Return a normalized configured upstream base URL."""

        field_name = f"gateway_{service}_service_url"
        return str(getattr(self, field_name)).rstrip("/")
