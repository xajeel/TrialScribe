"""Strict public-key verification for gateway access tokens."""

from datetime import UTC, datetime

import jwt
from pydantic import ValidationError

from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.schemas.auth import AccessClaims
from trialscribe_gateway.utils.constant import (
    ACCESS_TOKEN_ALGORITHM,
    ACCESS_TOKEN_REQUIRED_CLAIMS,
)
from trialscribe_gateway.utils.exceptions import InvalidAccessTokenError


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("token time must include a timezone")
    return value.astimezone(UTC)


class AccessTokenVerifier:
    """Validate access tokens without holding any signing capability."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def decode_access_token(self, token: str, now: datetime) -> AccessClaims:
        checked_at = _utc(now)
        try:
            payload = jwt.decode(
                token,
                self._settings.verification_key(),
                algorithms=[ACCESS_TOKEN_ALGORITHM],
                audience=self._settings.auth_jwt_audience,
                issuer=self._settings.auth_jwt_issuer,
                options={
                    "require": list(ACCESS_TOKEN_REQUIRED_CLAIMS),
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            claims = AccessClaims.model_validate(payload)
            if (
                claims.exp <= checked_at
                or claims.nbf > checked_at
                or claims.iat > checked_at
            ):
                raise ValueError("token time is invalid")
            return claims
        except (jwt.PyJWTError, ValidationError, TypeError, ValueError):
            raise InvalidAccessTokenError from None
