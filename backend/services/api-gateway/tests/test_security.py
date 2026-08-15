import base64
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import trialscribe_gateway.api.app as app_module
from trialscribe_gateway.api.app import create_app
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.constant import (
    INTERNAL_ACCOUNT_ID_HEADER,
    INTERNAL_ORGANIZATION_ID_HEADER,
    INVALID_AUTHENTICATION_DETAIL,
    ORGANIZATION_ACCESS_DENIED_DETAIL,
)

ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000091")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000092")
ORIGIN = "http://localhost:5173"
ATTACKER_ORIGIN = "https://attacker.example.com"
SPOOFED_ACCOUNT = "spoofed-client-account"
SPOOFED_ORGANIZATION = "spoofed-internal-organization"


class ChunkStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"ok"


def gateway_settings_and_token() -> tuple[GatewaySettings, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    settings = GatewaySettings(
        gateway_auth_service_url="http://auth.internal:8001",
        gateway_user_service_url="http://user.internal:8002",
        gateway_ai_service_url="http://ai.internal:8003",
        gateway_worker_service_url="http://worker.internal:8004",
        gateway_cors_origins=[ORIGIN],
        gateway_upstream_connect_timeout_seconds=2,
        gateway_upstream_read_timeout_seconds=60,
        gateway_upstream_write_timeout_seconds=60,
        gateway_upstream_pool_timeout_seconds=2,
        auth_jwt_public_key_b64=base64.b64encode(public_key).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(ACCOUNT_ID),
            "iss": settings.auth_jwt_issuer,
            "aud": settings.auth_jwt_audience,
            "iat": now - timedelta(seconds=1),
            "nbf": now - timedelta(seconds=1),
            "exp": now + timedelta(minutes=15),
            "jti": str(uuid4()),
            "type": "access",
        },
        private_key,
        algorithm="EdDSA",
    )
    return settings, token


@contextmanager
def assembled_client(
    monkeypatch: pytest.MonkeyPatch,
    settings: GatewaySettings,
    handler: Any,
) -> Iterator[TestClient]:
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        app_module.httpx,
        "AsyncClient",
        lambda **_kwargs: upstream_client,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_missing_authorization_on_jobs_is_one_safe_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, _token = gateway_settings_and_token()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream())

    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.get("/v1/jobs")

    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_AUTHENTICATION_DETAIL}
    assert "alg" not in response.text
    assert "HS256" not in response.text
    assert "Traceback" not in response.text


def test_spoofed_internal_headers_are_not_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, token = gateway_settings_and_token()
    captured: list[httpx.Headers] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers)
        if (
            request.url.host == "user.internal"
            and request.method == "GET"
            and request.url.path == f"/v1/organizations/{ORGANIZATION_ID}"
        ):
            return httpx.Response(200, json={"membership": "active"})
        return httpx.Response(200, stream=ChunkStream())

    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.get(
            "/v1/jobs",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-ID": str(ORGANIZATION_ID),
                INTERNAL_ACCOUNT_ID_HEADER: SPOOFED_ACCOUNT,
                INTERNAL_ORGANIZATION_ID_HEADER: SPOOFED_ORGANIZATION,
            },
        )

    assert response.status_code == 200
    forwarded = captured[-1]
    assert forwarded[INTERNAL_ACCOUNT_ID_HEADER.lower()] == str(ACCOUNT_ID)
    assert forwarded[INTERNAL_ORGANIZATION_ID_HEADER.lower()] == str(ORGANIZATION_ID)
    assert SPOOFED_ACCOUNT not in str(forwarded)
    assert SPOOFED_ORGANIZATION not in str(forwarded)
    assert SPOOFED_ACCOUNT not in response.text


def test_unknown_organization_is_forbidden_not_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, token = gateway_settings_and_token()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "user.internal":
            return httpx.Response(404, json={"detail": "hidden"})
        return httpx.Response(200, stream=ChunkStream())

    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.get(
            "/v1/jobs",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-ID": str(ORGANIZATION_ID),
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": ORGANIZATION_ACCESS_DENIED_DETAIL}
    assert "hidden" not in response.text
    assert response.status_code != 404


def test_cors_allows_configured_origin_and_rejects_attacker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, _token = gateway_settings_and_token()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream())

    with assembled_client(monkeypatch, settings, handler) as client:
        allowed = client.options(
            "/v1/auth/login",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,X-CSRF-Token",
            },
        )
        denied = client.options(
            "/v1/auth/login",
            headers={
                "Origin": ATTACKER_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in denied.headers
