import base64
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import BaseModel

import trialscribe_gateway.api.app as app_module
from trialscribe_gateway.config import GatewaySettings

ORIGIN = "http://localhost:5173"
SECRET = "postgresql://secret-leak:5432/db"


class ProbeBody(BaseModel):
    name: str


class LifecycleClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def aclose(self) -> None:
        return None


def install_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module.httpx, "AsyncClient", LifecycleClient)


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


def test_non_uuid_request_id_is_not_echoed_when_it_looks_like_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())

    with TestClient(application) as client:
        response = client.get("/health/live", headers={"X-Request-ID": SECRET})

    assert response.status_code == 200
    assert SECRET not in response.text


def test_validation_errors_strip_submitted_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(gateway_settings())

    @application.post("/validation-probe")
    async def probe(body: ProbeBody) -> ProbeBody:
        return body

    with TestClient(application) as client:
        response = client.post("/validation-probe", json={"name": [SECRET]})

    assert response.status_code == 422
    assert SECRET not in response.text
    assert all(
        "input" not in item
        for item in response.json()["detail"]
        if isinstance(item, dict)
    )
