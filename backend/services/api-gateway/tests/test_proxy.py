import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request

from trialscribe_gateway.api.proxy import GatewayProxy
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.enum import ProxyTarget
from trialscribe_gateway.utils.exceptions import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000061")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000062")
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000063")


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


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


def proxy_app(upstream_client: httpx.AsyncClient) -> FastAPI:
    settings = gateway_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.proxy = GatewayProxy(upstream_client, settings)
        yield

    application = FastAPI(lifespan=lifespan)

    @application.api_route(
        "/proxy/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def forward(request: Request, path: str) -> Any:
        request.state.request_id = REQUEST_ID
        return await request.app.state.proxy.forward(
            request,
            ProxyTarget.AUTH,
            f"/{path}",
            ACCOUNT_ID,
            ORGANIZATION_ID,
        )

    return application


@pytest.mark.anyio
async def test_proxy_preserves_contract_and_replaces_context_headers() -> None:
    captured: dict[str, Any] = {}

    async def upstream(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = await request.aread()
        response = httpx.Response(
            207,
            headers=[
                ("content-type", "application/octet-stream"),
                ("set-cookie", "first=one; Path=/"),
                ("set-cookie", "second=two; Path=/"),
                ("connection", "x-private"),
                ("x-private", "must-not-pass"),
            ],
            stream=ChunkStream(b"streamed-", b"response"),
        )
        captured["response"] = response
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        application = proxy_app(upstream_client)
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application),
                base_url="http://gateway.local",
            ) as client:
                response = await client.put(
                    "/proxy/resource?view=full",
                    content=b"streamed-request",
                    headers={
                        "Authorization": "Bearer signed-token",
                        "X-Organization-ID": "spoofed-public-context",
                        "X-TrialScribe-Account-ID": "spoofed-account",
                        "X-TrialScribe-Organization-ID": "spoofed-organization",
                        "X-Request-ID": "spoofed-request",
                    },
                )

    request: httpx.Request = captured["request"]
    assert request.method == "PUT"
    assert str(request.url) == "http://auth.internal:8001/resource?view=full"
    assert captured["body"] == b"streamed-request"
    assert request.headers["authorization"] == "Bearer signed-token"
    assert request.headers["x-request-id"] == str(REQUEST_ID)
    assert request.headers["x-trialscribe-account-id"] == str(ACCOUNT_ID)
    assert request.headers["x-trialscribe-organization-id"] == str(ORGANIZATION_ID)
    assert "x-organization-id" not in request.headers
    assert response.status_code == 207
    assert response.content == b"streamed-response"
    assert response.headers.get_list("set-cookie") == [
        "first=one; Path=/",
        "second=two; Path=/",
    ]
    assert "x-private" not in response.headers
    assert captured["response"].is_closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.ConnectError("internal secret"), UpstreamUnavailableError),
        (httpx.ReadTimeout("internal secret"), UpstreamTimeoutError),
    ],
)
async def test_proxy_translates_transport_failures(
    failure: httpx.RequestError,
    expected: type[Exception],
) -> None:
    async def upstream(_request: httpx.Request) -> httpx.Response:
        raise failure

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        application = proxy_app(upstream_client)
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application),
                base_url="http://gateway.local",
            ) as client:
                with pytest.raises(expected) as captured:
                    await client.get("/proxy/resource")

    assert str(captured.value) == ""


@pytest.mark.anyio
async def test_proxy_resolves_each_target_from_settings() -> None:
    seen_hosts: list[str] = []

    async def upstream(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        return httpx.Response(204, stream=ChunkStream())

    settings = gateway_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        proxy = GatewayProxy(upstream_client, settings)
        for target in ProxyTarget:
            application = FastAPI()

            @application.get("/")
            async def route(request: Request, selected: ProxyTarget = target) -> Any:
                request.state.request_id = REQUEST_ID
                return await proxy.forward(request, selected, "/health/live")

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application),
                base_url="http://gateway.local",
            ) as client:
                assert (await client.get("/")).status_code == 204

    assert seen_hosts == [
        "auth.internal",
        "user.internal",
        "ai.internal",
        "worker.internal",
    ]
