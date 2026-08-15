import base64
import hashlib
import hmac
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import ValidationError

import trialscribe_gateway.api.app as app_module
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.security.rate_limit import GatewayRateLimiter
from trialscribe_gateway.utils.constant import (
    RATE_LIMIT_FAMILY_API,
    RATE_LIMIT_FAMILY_AUTH,
    TOO_MANY_REQUESTS_DETAIL,
)

ORIGIN = "http://localhost:5173"
HMAC_SECRET = "test-rate-limit-secret"


class Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class LifecycleClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def aclose(self) -> None:
        return None


def install_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module.httpx, "AsyncClient", LifecycleClient)


def install_ok_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"{}"

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Body())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(app_module.httpx, "AsyncClient", lambda **_kwargs: client)


def gateway_settings(**overrides: object) -> GatewaySettings:
    public_key = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    values: dict[str, object] = {
        "gateway_auth_service_url": "http://auth.internal:8001",
        "gateway_user_service_url": "http://user.internal:8002",
        "gateway_ai_service_url": "http://ai.internal:8003",
        "gateway_worker_service_url": "http://worker.internal:8004",
        "gateway_cors_origins": [ORIGIN],
        "gateway_upstream_connect_timeout_seconds": 2,
        "gateway_upstream_read_timeout_seconds": 60,
        "gateway_upstream_write_timeout_seconds": 60,
        "gateway_upstream_pool_timeout_seconds": 2,
        "auth_jwt_public_key_b64": base64.b64encode(public_key).decode(),
        "auth_jwt_issuer": "trialscribe-auth",
        "auth_jwt_audience": "trialscribe-api",
        "gateway_rate_limit_hmac_secret": HMAC_SECRET,
    }
    values.update(overrides)
    return GatewaySettings(**values)


def test_api_family_denies_the_fourth_request_in_the_window() -> None:
    clock = Clock()
    limiter = GatewayRateLimiter(
        gateway_settings(gateway_rate_limit_requests=3),
        monotonic=clock,
    )

    allowed = [limiter.check("127.0.0.1", RATE_LIMIT_FAMILY_API) for _ in range(3)]
    denied = limiter.check("127.0.0.1", RATE_LIMIT_FAMILY_API)

    assert all(decision.allowed for decision in allowed)
    assert denied.allowed is False
    assert denied.retry_after is not None
    assert denied.retry_after >= 1


def test_auth_family_uses_its_own_limit() -> None:
    limiter = GatewayRateLimiter(
        gateway_settings(
            gateway_rate_limit_requests=3,
            gateway_rate_limit_auth_requests=1,
        ),
        monotonic=Clock(),
    )

    assert limiter.check("127.0.0.1", RATE_LIMIT_FAMILY_AUTH).allowed is True
    assert limiter.check("127.0.0.1", RATE_LIMIT_FAMILY_AUTH).allowed is False
    assert limiter.check("127.0.0.1", RATE_LIMIT_FAMILY_API).allowed is True


def test_health_metrics_and_options_are_not_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client_factory(monkeypatch)
    application = app_module.create_app(
        gateway_settings(gateway_rate_limit_requests=1),
    )

    with TestClient(application) as client:
        statuses = [
            client.get("/health/live").status_code,
            client.get("/health/live").status_code,
            client.get("/health/ready").status_code,
            client.get("/metrics").status_code,
            client.options(
                "/v1/auth/login",
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": "POST",
                },
            ).status_code,
        ]

    assert statuses == [200, 200, 200, 200, 200]


def test_auth_login_returns_safe_429_without_hmac_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_ok_upstream(monkeypatch)
    application = app_module.create_app(
        gateway_settings(gateway_rate_limit_auth_requests=1),
    )
    digest = hmac.new(
        HMAC_SECRET.encode(),
        f"{RATE_LIMIT_FAMILY_AUTH}\0testclient".encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(application) as client:
        client.post("/v1/auth/login")
        limited = client.post("/v1/auth/login")

    assert limited.status_code == 429
    assert limited.json() == {"detail": TOO_MANY_REQUESTS_DETAIL}
    assert limited.headers["retry-after"].isdigit()
    assert digest not in limited.text
    assert "trialscribe:gateway:rl:" not in limited.text


def test_zero_rate_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        gateway_settings(gateway_rate_limit_requests=0)
