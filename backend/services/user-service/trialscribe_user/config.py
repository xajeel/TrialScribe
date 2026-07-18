"""Environment-backed user and organization configuration."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _decode_public_key(value: Any) -> bytes:
    try:
        decoded = base64.b64decode(str(value), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("AUTH_JWT_PUBLIC_KEY_B64 must be valid base64") from None
    if len(decoded) != 32:
        raise ValueError("AUTH_JWT_PUBLIC_KEY_B64 must encode a 32-byte Ed25519 key")
    return decoded


class UserSettings(BaseSettings):
    """Validated settings required by the user-service boundary."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    auth_jwt_public_key_b64: str
    auth_jwt_issuer: str
    auth_jwt_audience: str
    user_invitation_ttl_seconds: int
    user_invitation_accept_url: AnyHttpUrl

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

    @field_validator("user_invitation_ttl_seconds")
    @classmethod
    def validate_invitation_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("invitation lifetime must be positive")
        return value

    def verification_key(self) -> Ed25519PublicKey:
        """Build the public-only key used to verify access tokens."""

        return Ed25519PublicKey.from_public_bytes(
            _decode_public_key(self.auth_jwt_public_key_b64)
        )

    def invitation_accept_url(self) -> str:
        """Return the configured absolute frontend invitation URL."""

        return str(self.user_invitation_accept_url)
