"""Environment-backed authentication configuration."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Self
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _secret_value(value: Any) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else str(value)


def _decode_key(value: Any, *, setting_name: str) -> bytes:
    try:
        decoded = base64.b64decode(_secret_value(value), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{setting_name} must be valid base64") from None
    if len(decoded) != 32:
        raise ValueError(f"{setting_name} must encode a 32-byte Ed25519 key")
    return decoded


class AuthSettings(BaseSettings):
    """Validated authentication settings with redacted secrets."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    auth_jwt_private_key_b64: SecretStr
    auth_jwt_public_key_b64: str
    auth_jwt_issuer: str
    auth_jwt_audience: str
    auth_access_token_ttl_seconds: int
    auth_refresh_token_ttl_seconds: int
    auth_cookie_secure: bool
    auth_hmac_secret: SecretStr
    auth_login_attempt_limit: int
    auth_login_window_seconds: int
    redis_url: SecretStr

    @field_validator("auth_jwt_private_key_b64", mode="before")
    @classmethod
    def validate_private_key(cls, value: Any) -> SecretStr:
        _decode_key(value, setting_name="AUTH_JWT_PRIVATE_KEY_B64")
        return SecretStr(_secret_value(value))

    @field_validator("auth_jwt_public_key_b64")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _decode_key(value, setting_name="AUTH_JWT_PUBLIC_KEY_B64")
        return value

    @field_validator("auth_jwt_issuer", "auth_jwt_audience")
    @classmethod
    def validate_token_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("token issuer and audience must not be empty")
        return value

    @field_validator(
        "auth_access_token_ttl_seconds",
        "auth_refresh_token_ttl_seconds",
        "auth_login_attempt_limit",
        "auth_login_window_seconds",
    )
    @classmethod
    def validate_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("authentication durations and limits must be positive")
        return value

    @field_validator("auth_hmac_secret", mode="before")
    @classmethod
    def validate_hmac_secret(cls, value: Any) -> SecretStr:
        raw_value = _secret_value(value)
        lowered = raw_value.casefold()
        if len(raw_value) < 32 or lowered.startswith(("change-me", "replace-me")):
            raise ValueError("AUTH_HMAC_SECRET must be a non-placeholder secret")
        return SecretStr(raw_value)

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, value: Any) -> SecretStr:
        raw_value = _secret_value(value)
        parsed = urlsplit(raw_value)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("REDIS_URL must be a valid Redis URL")
        if parsed.password is None:
            raise ValueError("REDIS_URL must include authentication")
        return SecretStr(raw_value)

    @model_validator(mode="after")
    def validate_authentication_contract(self) -> Self:
        if self.auth_refresh_token_ttl_seconds <= self.auth_access_token_ttl_seconds:
            raise ValueError("refresh token lifetime must exceed access token lifetime")

        private_key = self.signing_key()
        derived_public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        configured_public = _decode_key(
            self.auth_jwt_public_key_b64,
            setting_name="AUTH_JWT_PUBLIC_KEY_B64",
        )
        if derived_public != configured_public:
            raise ValueError("configured Ed25519 keys do not form a pair")
        return self

    def signing_key(self) -> Ed25519PrivateKey:
        """Reveal the private key only for token signing."""

        raw_key = _decode_key(
            self.auth_jwt_private_key_b64,
            setting_name="AUTH_JWT_PRIVATE_KEY_B64",
        )
        return Ed25519PrivateKey.from_private_bytes(raw_key)

    def verification_key(self) -> Ed25519PublicKey:
        """Build the public key used to verify access tokens."""

        raw_key = _decode_key(
            self.auth_jwt_public_key_b64,
            setting_name="AUTH_JWT_PUBLIC_KEY_B64",
        )
        return Ed25519PublicKey.from_public_bytes(raw_key)

    def redis_connection_url(self) -> str:
        """Reveal the Redis URL only for client construction."""

        return self.redis_url.get_secret_value()

    def hmac_key(self) -> bytes:
        """Reveal the HMAC key only for keyed security operations."""

        return self.auth_hmac_secret.get_secret_value().encode()
