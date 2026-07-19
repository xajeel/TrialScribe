"""Streaming reverse-proxy transport for internal services."""

from uuid import UUID

import httpx
from fastapi import Request, Response
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.constant import (
    HOP_BY_HOP_HEADERS,
    INTERNAL_ACCOUNT_ID_HEADER,
    INTERNAL_ORGANIZATION_ID_HEADER,
    ORGANIZATION_ID_HEADER,
    REQUEST_ID_HEADER,
)
from trialscribe_gateway.utils.enum import ProxyTarget
from trialscribe_gateway.utils.exceptions import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

_REQUEST_EXCLUDED_HEADERS = frozenset(
    {
        "host",
        "content-length",
        ORGANIZATION_ID_HEADER.casefold(),
        INTERNAL_ACCOUNT_ID_HEADER.casefold(),
        INTERNAL_ORGANIZATION_ID_HEADER.casefold(),
        REQUEST_ID_HEADER.casefold(),
    }
)
_RESPONSE_EXCLUDED_HEADERS = frozenset({"content-length"})


def _connection_headers(headers: httpx.Headers) -> set[str]:
    return {
        item.strip().casefold()
        for item in headers.get("connection", "").split(",")
        if item.strip()
    }


class GatewayProxy:
    """Forward one request without buffering its body or retrying writes."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: GatewaySettings,
    ) -> None:
        self._client = client
        self._settings = settings

    async def forward(
        self,
        request: Request,
        target: ProxyTarget,
        upstream_path: str,
        account_id: UUID | None = None,
        organization_id: UUID | None = None,
    ) -> Response:
        upstream_url = httpx.URL(
            f"{self._settings.service_url(target.value)}{upstream_path}",
            query=request.url.query.encode("ascii"),
        )
        excluded = (
            HOP_BY_HOP_HEADERS
            | _REQUEST_EXCLUDED_HEADERS
            | _connection_headers(httpx.Headers(request.headers.raw))
        )
        headers = [
            (name, value)
            for name, value in request.headers.raw
            if name.decode("latin-1").casefold() not in excluded
        ]
        headers.append((REQUEST_ID_HEADER.encode(), str(request.state.request_id).encode()))
        if account_id is not None:
            headers.append((INTERNAL_ACCOUNT_ID_HEADER.encode(), str(account_id).encode()))
        if organization_id is not None:
            headers.append(
                (INTERNAL_ORGANIZATION_ID_HEADER.encode(), str(organization_id).encode())
            )

        upstream_request = self._client.build_request(
            request.method,
            upstream_url,
            headers=headers,
            content=request.stream(),
        )
        try:
            upstream_response = await self._client.send(
                upstream_request,
                stream=True,
            )
        except httpx.TimeoutException:
            raise UpstreamTimeoutError from None
        except httpx.RequestError:
            raise UpstreamUnavailableError from None

        response = StreamingResponse(
            upstream_response.aiter_raw(),
            status_code=upstream_response.status_code,
            background=BackgroundTask(upstream_response.aclose),
        )
        response_excluded = (
            HOP_BY_HOP_HEADERS
            | _RESPONSE_EXCLUDED_HEADERS
            | _connection_headers(upstream_response.headers)
        )
        for name, value in upstream_response.headers.multi_items():
            if name.casefold() not in response_excluded:
                response.headers.append(name, value)
        return response
