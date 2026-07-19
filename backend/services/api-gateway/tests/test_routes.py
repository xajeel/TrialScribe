import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from trialscribe_gateway.api.dependencies import get_now, get_token_verifier
from trialscribe_gateway.api.routes import (
    get_gateway_proxy,
    get_organization_access_service,
    router,
)
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.services.organization_access import OrganizationAccessService
from trialscribe_gateway.utils.enum import ProxyTarget
from trialscribe_gateway.utils.exceptions import InvalidAccessTokenError

ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000071")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000072")
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000073")
NOW = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)


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
        gateway_cors_origins=["http://localhost:5173"],
        gateway_upstream_connect_timeout_seconds=2,
        gateway_upstream_read_timeout_seconds=60,
        gateway_upstream_write_timeout_seconds=60,
        gateway_upstream_pool_timeout_seconds=2,
        auth_jwt_public_key_b64=base64.b64encode(public_key).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
    )


class FakeVerifier:
    def decode_access_token(self, token: str, _now: datetime) -> Any:
        if token == "invalid":
            raise InvalidAccessTokenError
        return SimpleNamespace(sub=ACCOUNT_ID)


class FakeProxy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def forward(
        self,
        request: Request,
        target: ProxyTarget,
        upstream_path: str,
        account_id: UUID | None = None,
        organization_id: UUID | None = None,
    ) -> JSONResponse:
        call = {
            "method": request.method,
            "target": target.value,
            "path": upstream_path,
            "account_id": str(account_id) if account_id else None,
            "organization_id": str(organization_id) if organization_id else None,
        }
        self.calls.append(call)
        return JSONResponse(call)


class FakeOrganizationAccess:
    def __init__(self) -> None:
        self.status_code = 200
        self.calls: list[tuple[str, UUID, UUID]] = []

    async def membership_status(
        self,
        bearer_token: str,
        organization_id: UUID,
        request_id: UUID,
    ) -> int:
        self.calls.append((bearer_token, organization_id, request_id))
        return self.status_code


@pytest.fixture
def api_context() -> dict[str, Any]:
    proxy = FakeProxy()
    access = FakeOrganizationAccess()
    application = FastAPI()

    @application.middleware("http")
    async def request_id(request: Request, call_next: Any) -> Any:
        request.state.request_id = REQUEST_ID
        return await call_next(request)

    application.include_router(router)
    application.dependency_overrides[get_gateway_proxy] = lambda: proxy
    application.dependency_overrides[get_organization_access_service] = lambda: access
    application.dependency_overrides[get_token_verifier] = lambda: FakeVerifier()
    application.dependency_overrides[get_now] = lambda: NOW
    return {"client": TestClient(application), "proxy": proxy, "access": access}


@pytest.mark.parametrize("path", ["register", "login", "refresh", "logout"])
def test_public_auth_operations_are_anonymous(
    api_context: dict[str, Any],
    path: str,
) -> None:
    response = api_context["client"].post(f"/v1/auth/{path}")

    assert response.status_code == 200
    assert response.json()["path"] == f"/v1/auth/{path}"
    assert response.json()["account_id"] is None


def test_unknown_auth_and_user_routes_require_bearer(
    api_context: dict[str, Any],
) -> None:
    responses = [
        api_context["client"].get("/v1/auth/unknown"),
        api_context["client"].get("/v1/organizations"),
    ]

    assert [response.status_code for response in responses] == [401, 401]
    assert all(
        response.json() == {"detail": "Invalid authentication credentials"}
        for response in responses
    )
    assert api_context["proxy"].calls == []


@pytest.mark.parametrize(
    ("method", "path", "target", "upstream", "organization_id"),
    [
        ("GET", "/v1/organizations", "user", "/v1/organizations", None),
        (
            "PATCH",
            f"/v1/organizations/{ORGANIZATION_ID}/members/target",
            "user",
            f"/v1/organizations/{ORGANIZATION_ID}/members/target",
            str(ORGANIZATION_ID),
        ),
        (
            "POST",
            "/v1/organization-invitations/accept",
            "user",
            "/v1/organization-invitations/accept",
            None,
        ),
    ],
)
def test_user_routes_preserve_paths_and_context(
    api_context: dict[str, Any],
    method: str,
    path: str,
    target: str,
    upstream: str,
    organization_id: str | None,
) -> None:
    response = api_context["client"].request(
        method,
        path,
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "method": method,
        "target": target,
        "path": upstream,
        "account_id": str(ACCOUNT_ID),
        "organization_id": organization_id,
    }


@pytest.mark.parametrize(
    ("path", "target", "upstream"),
    [
        ("/v1/ai/sessions/one", "ai", "/sessions/one"),
        ("/v1/jobs/job-one", "worker", "/job-one"),
    ],
)
def test_capability_routes_verify_membership_and_strip_prefix(
    api_context: dict[str, Any],
    path: str,
    target: str,
    upstream: str,
) -> None:
    response = api_context["client"].get(
        path,
        headers={
            "Authorization": "Bearer valid",
            "X-Organization-ID": str(ORGANIZATION_ID),
        },
    )

    assert response.status_code == 200
    assert response.json()["target"] == target
    assert response.json()["path"] == upstream
    assert response.json()["organization_id"] == str(ORGANIZATION_ID)
    assert api_context["access"].calls[-1] == (
        "valid",
        ORGANIZATION_ID,
        REQUEST_ID,
    )


@pytest.mark.parametrize(
    ("membership_status", "expected_status", "expected_detail"),
    [
        (401, 401, "Invalid authentication credentials"),
        (403, 403, "Organization access denied"),
        (404, 403, "Organization access denied"),
    ],
)
def test_membership_rejections_are_stable(
    api_context: dict[str, Any],
    membership_status: int,
    expected_status: int,
    expected_detail: str,
) -> None:
    api_context["access"].status_code = membership_status

    response = api_context["client"].get(
        "/v1/ai/sessions",
        headers={
            "Authorization": "Bearer valid",
            "X-Organization-ID": str(ORGANIZATION_ID),
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert api_context["proxy"].calls == []


def test_missing_or_invalid_organization_header_is_rejected(
    api_context: dict[str, Any],
) -> None:
    responses = [
        api_context["client"].get(
            "/v1/jobs/one",
            headers={"Authorization": "Bearer valid"},
        ),
        api_context["client"].get(
            "/v1/jobs/one",
            headers={
                "Authorization": "Bearer valid",
                "X-Organization-ID": "not-a-uuid",
            },
        ),
    ]

    assert [response.status_code for response in responses] == [422, 422]
    assert all(
        response.json() == {"detail": "Invalid organization context"}
        for response in responses
    )


@pytest.mark.anyio
async def test_membership_service_forwards_token_and_request_id() -> None:
    captured: dict[str, httpx.Request] = {}

    async def user_service(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(user_service)) as client:
        status_code = await OrganizationAccessService(
            client,
            gateway_settings(),
        ).membership_status("signed-token", ORGANIZATION_ID, REQUEST_ID)

    request = captured["request"]
    assert status_code == 200
    assert request.url.path == f"/v1/organizations/{ORGANIZATION_ID}"
    assert request.headers["authorization"] == "Bearer signed-token"
    assert request.headers["x-request-id"] == str(REQUEST_ID)
