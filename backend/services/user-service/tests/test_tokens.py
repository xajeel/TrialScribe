import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trialscribe_user.config import UserSettings
from trialscribe_user.security.tokens import (
    AccessTokenVerifier,
    InvalidAccessTokenError,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000001")


def verifier_context() -> tuple[AccessTokenVerifier, Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    settings = UserSettings(
        auth_jwt_public_key_b64=base64.b64encode(public_key).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
        user_invitation_ttl_seconds=604800,
        user_invitation_accept_url="https://app.example.com/invitations/accept",
    )
    return AccessTokenVerifier(settings), private_key


def payload(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": str(ACCOUNT_ID),
        "iss": "trialscribe-auth",
        "aud": "trialscribe-api",
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + timedelta(minutes=15),
        "jti": str(uuid4()),
        "type": "access",
    }
    claims.update(overrides)
    return claims


def issue(private_key: Ed25519PrivateKey, claims: dict[str, object]) -> str:
    return jwt.encode(claims, private_key, algorithm="EdDSA")


def test_valid_access_token_is_verified_with_public_key_only() -> None:
    verifier, private_key = verifier_context()

    claims = verifier.decode_access_token(issue(private_key, payload()), NOW)

    assert claims.sub == ACCOUNT_ID
    assert claims.type == "access"
    assert not hasattr(verifier, "issue_access_token")


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "other"},
        {"aud": "other"},
        {"type": "refresh"},
        {"exp": NOW},
        {"nbf": NOW + timedelta(seconds=1)},
        {"iat": NOW + timedelta(seconds=1)},
        {"sub": "not-a-uuid"},
    ],
)
def test_invalid_claims_share_one_safe_error(overrides: dict[str, object]) -> None:
    verifier, private_key = verifier_context()

    with pytest.raises(InvalidAccessTokenError, match="Invalid authentication credentials"):
        verifier.decode_access_token(issue(private_key, payload(**overrides)), NOW)


def test_missing_required_claim_tampering_and_wrong_key_are_rejected() -> None:
    verifier, private_key = verifier_context()
    missing = payload()
    del missing["jti"]
    other_key = Ed25519PrivateKey.generate()
    tokens = [
        issue(private_key, missing),
        f"{issue(private_key, payload())}x",
        issue(other_key, payload()),
        "not-a-token",
    ]

    for token in tokens:
        with pytest.raises(InvalidAccessTokenError):
            verifier.decode_access_token(token, NOW)
