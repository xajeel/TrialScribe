import base64
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import trialscribe_gateway.api.app as app_module
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.constant import (
    CACHE_CONTROL_HEADER,
    CACHE_CONTROL_VALUE,
    CONTENT_SECURITY_POLICY_HEADER,
    CONTENT_SECURITY_POLICY_VALUE,
    DOCS_CONTENT_SECURITY_POLICY_VALUE,
    CONTENT_TYPE_OPTIONS_HEADER,
    CONTENT_TYPE_OPTIONS_VALUE,
    FRAME_OPTIONS_HEADER,
    FRAME_OPTIONS_VALUE,
    PERMISSIONS_POLICY_HEADER,
    PERMISSIONS_POLICY_VALUE,
    REFERRER_POLICY_HEADER,
    REFERRER_POLICY_VALUE,
    SERVICE_UNAVAILABLE_DETAIL,
)
from trialscribe_gateway.utils.exceptions import UpstreamUnavailableError

ORIGIN = "http://localhost:5173"


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


def _assert_secure_headers(headers: object) -> None:
    assert headers[CONTENT_TYPE_OPTIONS_HEADER] == CONTENT_TYPE_OPTIONS_VALUE
    assert headers[FRAME_OPTIONS_HEADER] == FRAME_OPTIONS_VALUE
    assert headers[REFERRER_POLICY_HEADER] == REFERRER_POLICY_VALUE
    assert headers[CACHE_CONTROL_HEADER] == CACHE_CONTROL_VALUE
    assert headers[CONTENT_SECURITY_POLICY_HEADER] == CONTENT_SECURITY_POLICY_VALUE
    assert headers[PERMISSIONS_POLICY_HEADER] == PERMISSIONS_POLICY_VALUE


def test_docs_allow_swagger_assets_under_a_narrower_csp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())

    with TestClient(application) as client:
        docs = client.get("/docs")
        spec = client.get("/openapi.json")

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    assert docs.headers[CONTENT_SECURITY_POLICY_HEADER] == (
        DOCS_CONTENT_SECURITY_POLICY_VALUE
    )
    assert spec.status_code == 200
    assert spec.headers[CONTENT_SECURITY_POLICY_HEADER] == (
        DOCS_CONTENT_SECURITY_POLICY_VALUE
    )


def test_health_and_metrics_carry_secure_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())

    with TestClient(application) as client:
        live = client.get("/health/live")
        metrics = client.get("/metrics")

    assert live.status_code == 200
    _assert_secure_headers(live.headers)
    assert metrics.status_code == 200
    assert metrics.headers[CONTENT_TYPE_OPTIONS_HEADER] == CONTENT_TYPE_OPTIONS_VALUE
    assert metrics.headers[CACHE_CONTROL_HEADER] == CACHE_CONTROL_VALUE


def test_error_responses_carry_secure_headers_without_internals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())
    error = UpstreamUnavailableError("internal host secret")

    @application.get("/failure")
    async def failure() -> None:
        raise error

    with TestClient(application) as client:
        response = client.get("/failure")

    assert response.status_code == 503
    assert response.json() == {"detail": SERVICE_UNAVAILABLE_DETAIL}
    assert str(error) not in response.text
    assert response.headers[FRAME_OPTIONS_HEADER] == FRAME_OPTIONS_VALUE
