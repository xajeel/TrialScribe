import base64
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.schemas.auth import TokenResponse
from trialscribe_auth.security.tokens import AccessTokenCodec, InvalidAccessTokenError


def settings_values() -> dict[str, Any]:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "auth_jwt_private_key_b64": base64.b64encode(private_bytes).decode(),
        "auth_jwt_public_key_b64": base64.b64encode(public_bytes).decode(),
        "auth_jwt_issuer": "trialscribe-auth",
        "auth_jwt_audience": "trialscribe-api",
        "auth_access_token_ttl_seconds": 900,
        "auth_refresh_token_ttl_seconds": 2_592_000,
        "auth_cookie_secure": False,
        "auth_hmac_secret": secrets.token_urlsafe(32),
        "auth_login_attempt_limit": 5,
        "auth_login_window_seconds": 300,
        "redis_url": "redis://:private-password@localhost:6379/0",
    }


def auth_settings(**overrides: Any) -> AuthSettings:
    values = settings_values()
    values.update(overrides)
    return AuthSettings(**values)


def test_valid_access_claims_round_trip() -> None:
    settings = auth_settings()
    codec = AccessTokenCodec(settings)
    now = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    account_id = uuid4()

    token = codec.issue_access_token(account_id, now)
    claims = codec.decode_access_token(token, now)

    assert claims.sub == account_id
    assert claims.iss == "trialscribe-auth"
    assert claims.aud == "trialscribe-api"
    assert claims.iat == now
    assert claims.nbf == now
    assert claims.exp == now + timedelta(seconds=900)
    assert claims.type == "access"


def test_token_response_never_contains_refresh_credentials() -> None:
    response = TokenResponse(access_token="short-lived", expires_in=900)

    assert response.model_dump() == {
        "access_token": "short-lived",
        "token_type": "bearer",
        "expires_in": 900,
    }
    assert "refresh" not in TokenResponse.model_fields


@pytest.mark.parametrize("time_offset", [-1, 901])
def test_early_and_expired_tokens_share_one_safe_error(time_offset: int) -> None:
    codec = AccessTokenCodec(auth_settings())
    issued_at = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    token = codec.issue_access_token(uuid4(), issued_at)

    with pytest.raises(InvalidAccessTokenError) as captured:
        codec.decode_access_token(token, issued_at + timedelta(seconds=time_offset))

    assert str(captured.value) == "Invalid authentication credentials"


@pytest.mark.parametrize(
    "changed_claim",
    [
        {"iss": "wrong-issuer"},
        {"aud": "wrong-audience"},
        {"type": "refresh"},
        {"sub": "not-a-uuid"},
        {"jti": "not-a-uuid"},
    ],
)
def test_wrong_or_malformed_claims_share_one_safe_error(
    changed_claim: dict[str, str],
) -> None:
    settings = auth_settings()
    codec = AccessTokenCodec(settings)
    now = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    payload = {
        "sub": str(uuid4()),
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
        "jti": str(uuid4()),
        "type": "access",
        **changed_claim,
    }
    token = jwt.encode(payload, settings.signing_key(), algorithm="EdDSA")

    with pytest.raises(InvalidAccessTokenError) as captured:
        codec.decode_access_token(token, now)

    assert str(captured.value) == "Invalid authentication credentials"


def test_missing_claim_is_rejected() -> None:
    settings = auth_settings()
    codec = AccessTokenCodec(settings)
    now = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iss": settings.auth_jwt_issuer,
            "aud": settings.auth_jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=15),
            "type": "access",
        },
        settings.signing_key(),
        algorithm="EdDSA",
    )

    with pytest.raises(InvalidAccessTokenError):
        codec.decode_access_token(token, now)


@pytest.mark.parametrize("token", ["", "not-a-token", "a.b.c"])
def test_malformed_token_never_escapes_library_details(token: str) -> None:
    codec = AccessTokenCodec(auth_settings())

    with pytest.raises(InvalidAccessTokenError) as captured:
        codec.decode_access_token(token, datetime.now(UTC))

    assert str(captured.value) == "Invalid authentication credentials"
    assert token not in str(captured.value) or not token


def test_token_signed_by_another_key_is_rejected() -> None:
    now = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    untrusted_codec = AccessTokenCodec(auth_settings())
    trusted_codec = AccessTokenCodec(auth_settings())
    token = untrusted_codec.issue_access_token(uuid4(), now)

    with pytest.raises(InvalidAccessTokenError):
        trusted_codec.decode_access_token(token, now)


def test_naive_time_is_rejected_before_token_processing() -> None:
    codec = AccessTokenCodec(auth_settings())

    with pytest.raises(ValueError, match="timezone"):
        codec.issue_access_token(uuid4(), datetime(2026, 7, 18, 9, 30))
