import base64
import importlib
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

from trialscribe_gateway.api.app import create_app
from trialscribe_gateway.config import GatewaySettings

gateway_app_module = importlib.import_module("trialscribe_gateway.api.app")

ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000081")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000082")
SUPPLIED_REQUEST_ID = UUID("00000000-0000-4000-8000-000000000083")
INTERNAL_ACCOUNT_HEADER = "X-TrialScribe-Account-ID"
INTERNAL_ORGANIZATION_HEADER = "X-TrialScribe-Organization-ID"


class ChunkStream(httpx.AsyncByteStream):
    """Ensure the proxy consumes a genuinely streamed upstream response."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"upstream-"
        yield b"response"


def settings_and_token() -> tuple[GatewaySettings, str]:
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
        gateway_cors_origins=["http://localhost:5173"],
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


async def snapshot(request: httpx.Request) -> dict[str, Any]:
    return {
        "method": request.method,
        "host": request.url.host,
        "path": request.url.path,
        "query": request.url.query.decode(),
        "body": await request.aread(),
        "headers": dict(request.headers),
    }


def streamed_response(status_code: int = 207) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=[
            ("content-type", "text/plain"),
            ("set-cookie", "first=one; Path=/; HttpOnly"),
            ("set-cookie", "second=two; Path=/; HttpOnly"),
            ("x-upstream-safe", "kept"),
            ("connection", "x-upstream-private"),
            ("x-upstream-private", "must-not-leak"),
        ],
        stream=ChunkStream(),
    )


@contextmanager
def assembled_client(
    monkeypatch: pytest.MonkeyPatch,
    settings: GatewaySettings,
    handler: Any,
) -> Iterator[TestClient]:
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        gateway_app_module.httpx,
        "AsyncClient",
        lambda **_kwargs: upstream_client,
    )
    with TestClient(create_app(settings)) as client:
        yield client
    assert upstream_client.is_closed


@pytest.mark.parametrize(
    ("method", "public_path", "upstream_host", "upstream_path"),
    [
        ("POST", "/v1/auth/login", "auth.internal", "/v1/auth/login"),
        ("PATCH", "/v1/organizations", "user.internal", "/v1/organizations"),
        (
            "POST",
            "/v1/organization-invitations/accept",
            "user.internal",
            "/v1/organization-invitations/accept",
        ),
        ("PUT", "/v1/ai/sessions/session-one", "ai.internal", "/sessions/session-one"),
        ("DELETE", "/v1/jobs/job-one", "worker.internal", "/jobs/job-one"),
    ],
)
def test_each_public_prefix_preserves_the_proxy_contract(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    public_path: str,
    upstream_host: str,
    upstream_path: str,
) -> None:
    settings, token = settings_and_token()
    calls: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(await snapshot(request))
        if (
            request.url.host == "user.internal"
            and request.method == "GET"
            and request.url.path == f"/v1/organizations/{ORGANIZATION_ID}"
        ):
            return httpx.Response(200, json={"membership": "active"})
        return streamed_response()

    request_id = str(uuid4())
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Request-ID": request_id,
    }
    if public_path.startswith(("/v1/ai/", "/v1/jobs/")):
        headers["X-Organization-ID"] = str(ORGANIZATION_ID)

    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.request(
            method,
            f"{public_path}?view=full",
            headers=headers,
            content=b'{"payload":"stream-me"}',
        )

    destination = calls[-1]
    assert destination["method"] == method
    assert destination["host"] == upstream_host
    assert destination["path"] == upstream_path
    assert destination["query"] == "view=full"
    assert destination["body"] == b'{"payload":"stream-me"}'
    assert destination["headers"]["authorization"] == f"Bearer {token}"
    assert response.status_code == 207
    assert response.content == b"upstream-response"
    assert response.headers.get_list("set-cookie") == [
        "first=one; Path=/; HttpOnly",
        "second=two; Path=/; HttpOnly",
    ]
    assert response.headers["x-upstream-safe"] == "kept"
    assert "x-upstream-private" not in response.headers


def test_anonymous_calls_stop_and_internal_header_spoofing_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, token = settings_and_token()
    calls: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(await snapshot(request))
        return streamed_response(200)

    with assembled_client(monkeypatch, settings, handler) as client:
        anonymous = client.get("/v1/organizations")
        unknown_auth = client.get("/v1/auth/private-operation")
        assert calls == []

        response = client.patch(
            f"/v1/organizations/{ORGANIZATION_ID}/members/member-one",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-ID": "spoofed-client-organization",
                INTERNAL_ACCOUNT_HEADER: "spoofed-client-account",
                INTERNAL_ORGANIZATION_HEADER: "spoofed-internal-organization",
            },
        )

    assert anonymous.status_code == 401
    assert unknown_auth.status_code == 401
    assert response.status_code == 200
    forwarded = calls[0]
    assert forwarded["headers"][INTERNAL_ACCOUNT_HEADER.lower()] == str(ACCOUNT_ID)
    assert forwarded["headers"][INTERNAL_ORGANIZATION_HEADER.lower()] == str(
        ORGANIZATION_ID
    )
    assert "x-organization-id" not in forwarded["headers"]
    assert "spoofed" not in repr(forwarded)


@pytest.mark.parametrize("supplied", [str(SUPPLIED_REQUEST_ID), None])
def test_correlation_id_reaches_membership_destination_and_response(
    monkeypatch: pytest.MonkeyPatch,
    supplied: str | None,
) -> None:
    settings, token = settings_and_token()
    calls: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(await snapshot(request))
        if request.url.host == "user.internal":
            return httpx.Response(200, json={"membership": "active"})
        return streamed_response(200)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(ORGANIZATION_ID),
    }
    if supplied is not None:
        headers["X-Request-ID"] = supplied
    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.post("/v1/ai/sessions", headers=headers)

    observed = response.headers["x-request-id"]
    assert UUID(observed)
    if supplied is not None:
        assert observed == supplied
    assert [call["headers"]["x-request-id"] for call in calls] == [
        observed,
        observed,
    ]
    membership, destination = calls
    assert membership["path"] == f"/v1/organizations/{ORGANIZATION_ID}"
    assert membership["headers"]["authorization"] == f"Bearer {token}"
    assert destination["host"] == "ai.internal"
    assert destination["headers"][INTERNAL_ACCOUNT_HEADER.lower()] == str(ACCOUNT_ID)
    assert destination["headers"][INTERNAL_ORGANIZATION_HEADER.lower()] == str(
        ORGANIZATION_ID
    )


@pytest.mark.parametrize(
    ("error_type", "status_code", "detail"),
    [
        (httpx.ConnectError, 503, "Service unavailable"),
        (httpx.ReadTimeout, 504, "Service request timed out"),
    ],
)
def test_upstream_failures_are_fixed_safe_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[httpx.RequestError],
    status_code: int,
    detail: str,
) -> None:
    settings, _token = settings_and_token()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise error_type("private-upstream-secret", request=request)

    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.post(
            "/v1/auth/login",
            content=b'{"password":"client-secret"}',
        )

    assert attempts == 1
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert "private-upstream-secret" not in response.text
    assert "client-secret" not in response.text
    assert UUID(response.headers["x-request-id"])


@pytest.mark.parametrize("path", ["/v1/ai/sessions", "/v1/jobs/job-one"])
def test_membership_timeouts_are_safe_504_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    settings, token = settings_and_token()
    attempts = 0
    request_id = str(uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        assert request.url.host == "user.internal"
        raise httpx.ReadTimeout("private membership detail", request=request)

    with assembled_client(monkeypatch, settings, handler) as client:
        response = client.post(
            path,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-ID": str(ORGANIZATION_ID),
                "X-Request-ID": request_id,
            },
        )

    assert attempts == 1
    assert response.status_code == 504
    assert response.json() == {"detail": "Service request timed out"}
    assert response.headers["x-request-id"] == request_id
    assert "private membership detail" not in response.text
