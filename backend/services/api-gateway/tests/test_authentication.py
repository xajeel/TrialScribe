import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from trialscribe_gateway.api.dependencies import (
    get_current_account_id,
    get_now,
    get_settings,
)
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.security.tokens import AccessTokenVerifier
from trialscribe_gateway.utils.exceptions import InvalidAccessTokenError

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000051")


def settings_and_key() -> tuple[GatewaySettings, Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    raw_public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    settings = GatewaySettings(
        gateway_auth_service_url="http://127.0.0.1:8001",
        gateway_user_service_url="http://127.0.0.1:8002",
        gateway_ai_service_url="http://127.0.0.1:8003",
        gateway_worker_service_url="http://127.0.0.1:8004",
        gateway_cors_origins=["http://localhost:5173"],
        gateway_upstream_connect_timeout_seconds=2,
        gateway_upstream_read_timeout_seconds=60,
        gateway_upstream_write_timeout_seconds=60,
        gateway_upstream_pool_timeout_seconds=2,
        auth_jwt_public_key_b64=base64.b64encode(raw_public_key).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
    )
    return settings, private_key


def issue_token(
    private_key: Ed25519PrivateKey,
    **overrides: object,
) -> str:
    payload: dict[str, object] = {
        "sub": str(ACCOUNT_ID),
        "iss": "trialscribe-auth",
        "aud": "trialscribe-api",
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + timedelta(minutes=15),
        "jti": str(uuid4()),
        "type": "access",
    }
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="EdDSA")


def test_valid_token_returns_strict_claims() -> None:
    settings, private_key = settings_and_key()

    claims = AccessTokenVerifier(settings).decode_access_token(
        issue_token(private_key),
        NOW,
    )

    assert claims.sub == ACCOUNT_ID
    assert claims.type == "access"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": NOW - timedelta(seconds=1)},
        {"iat": NOW + timedelta(seconds=1)},
        {"nbf": NOW + timedelta(seconds=1)},
        {"iss": "wrong-issuer"},
        {"aud": "wrong-audience"},
        {"type": "refresh"},
        {"jti": None},
    ],
)
def test_invalid_claims_share_one_exception(overrides: dict[str, object]) -> None:
    settings, private_key = settings_and_key()

    with pytest.raises(InvalidAccessTokenError) as captured:
        AccessTokenVerifier(settings).decode_access_token(
            issue_token(private_key, **overrides),
            NOW,
        )

    assert str(captured.value) == ""


def test_protected_dependency_returns_one_safe_401() -> None:
    settings, private_key = settings_and_key()
    application = FastAPI()

    @application.get("/protected")
    async def protected(account_id: UUID = Depends(get_current_account_id)) -> str:
        return str(account_id)

    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_now] = lambda: NOW
    client = TestClient(application)
    valid = issue_token(private_key)
    responses = [
        client.get("/protected"),
        client.get("/protected", headers={"Authorization": "Bearer malformed"}),
        client.get(
            "/protected",
            headers={"Authorization": f"Bearer {valid}x"},
        ),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert all(
        response.json() == {"detail": "Invalid authentication credentials"}
        for response in responses
    )
    assert all(response.headers["www-authenticate"] == "Bearer" for response in responses)


def test_valid_dependency_extracts_account_id() -> None:
    settings, private_key = settings_and_key()
    application = FastAPI()

    @application.get("/protected")
    async def protected(account_id: UUID = Depends(get_current_account_id)) -> str:
        return str(account_id)

    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_now] = lambda: NOW

    response = TestClient(application).get(
        "/protected",
        headers={"Authorization": f"Bearer {issue_token(private_key)}"},
    )

    assert response.status_code == 200
    assert response.json() == str(ACCOUNT_ID)
