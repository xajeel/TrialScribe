import base64
from typing import Any
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

import trialscribe_gateway.api.app as app_module
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.exceptions import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

ORIGIN = "http://localhost:5173"
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000081")


def gateway_settings() -> GatewaySettings:
    public_key = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return GatewaySettings(
        gateway_auth_service_url="http://auth.internal:8001",
        gateway_user_service_url="http://user.internal:8002",
        gateway_ai_service_url="http://ai.internal:8003",
        gateway_worker_service_url="http://worker.internal:8004",
        gateway_cors_origins=[ORIGIN],
        gateway_upstream_connect_timeout_seconds=2,
        gateway_upstream_read_timeout_seconds=61,
        gateway_upstream_write_timeout_seconds=62,
        gateway_upstream_pool_timeout_seconds=3,
        auth_jwt_public_key_b64=base64.b64encode(public_key).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
    )


class LifecycleClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.is_closed = False

    async def aclose(self) -> None:
        self.is_closed = True


def install_client_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[LifecycleClient]:
    clients: list[LifecycleClient] = []

    def factory(**kwargs: Any) -> LifecycleClient:
        client = LifecycleClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(app_module.httpx, "AsyncClient", factory)
    return clients


def test_lifespan_owns_one_configured_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = gateway_settings()
    clients = install_client_factory(monkeypatch)
    application = app_module.create_app(settings)

    with TestClient(application) as client:
        assert client.get("/health/ready").status_code == 200
        assert application.state.gateway_settings is settings
        assert application.state.http_client is clients[0]
        timeout: httpx.Timeout = clients[0].kwargs["timeout"]
        assert timeout.connect == 2
        assert timeout.read == 61
        assert timeout.write == 62
        assert timeout.pool == 3
        assert clients[0].kwargs["follow_redirects"] is False

    assert clients[0].is_closed is True
    assert application.state.gateway_ready is False


def test_request_ids_are_preserved_or_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())

    with TestClient(application) as client:
        preserved = client.get(
            "/health/live",
            headers={"X-Request-ID": str(REQUEST_ID)},
        )
        generated = client.get(
            "/health/live",
            headers={"X-Request-ID": "not-a-uuid"},
        )

    assert preserved.headers["x-request-id"] == str(REQUEST_ID)
    assert UUID(generated.headers["x-request-id"])


def test_cors_allows_only_configured_origin_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())

    with TestClient(application) as client:
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
                "Origin": "https://attacker.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (UpstreamUnavailableError("internal host secret"), 503, "Service unavailable"),
        (UpstreamTimeoutError("internal timeout secret"), 504, "Service request timed out"),
    ],
)
def test_custom_errors_are_safe_and_keep_request_id(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    install_client_factory(monkeypatch)
    application: FastAPI = app_module.create_app(gateway_settings())

    @application.get("/failure")
    async def failure() -> None:
        raise error

    with TestClient(application) as client:
        response = client.get(
            "/failure",
            headers={"X-Request-ID": str(REQUEST_ID)},
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert response.headers["x-request-id"] == str(REQUEST_ID)
    assert str(error) not in response.text
