"""Ed25519 access-token issuance and strict validation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pydantic import ValidationError

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.schemas.auth import AccessClaims
from trialscribe_auth.utils.constant import (
    ACCESS_TOKEN_ALGORITHM,
    ACCESS_TOKEN_REQUIRED_CLAIMS,
)
from trialscribe_auth.utils.exceptions import InvalidAccessTokenError


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("token time must include a timezone")
    return value.astimezone(UTC)


class AccessTokenCodec:
    """Issue and validate access tokens using one configured key pair."""

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings

    def issue_access_token(self, account_id: UUID, now: datetime) -> str:
        issued_at = _utc(now)
        expires_at = issued_at + timedelta(
            seconds=self._settings.auth_access_token_ttl_seconds
        )
        payload = {
            "sub": str(account_id),
            "iss": self._settings.auth_jwt_issuer,
            "aud": self._settings.auth_jwt_audience,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
            "jti": str(uuid4()),
            "type": "access",
        }
        return jwt.encode(
            payload,
            self._settings.signing_key(),
            algorithm=ACCESS_TOKEN_ALGORITHM,
        )

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
            raise InvalidAccessTokenError(
                "Invalid authentication credentials"
            ) from None
