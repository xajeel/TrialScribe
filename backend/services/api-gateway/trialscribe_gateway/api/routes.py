"""Versioned reverse-proxy routes for backend service boundaries."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from httpx import AsyncClient

from trialscribe_gateway.api.dependencies import (
    authentication_error,
    get_current_account_id,
    get_http_client,
    get_now,
    get_optional_bearer_token,
    get_settings,
    get_token_verifier,
)
from trialscribe_gateway.api.proxy import GatewayProxy
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.security.tokens import AccessTokenVerifier
from trialscribe_gateway.services.organization_access import OrganizationAccessService
from trialscribe_gateway.utils.constant import (
    INVALID_ORGANIZATION_DETAIL,
    ORGANIZATION_ACCESS_DENIED_DETAIL,
    ORGANIZATION_ID_HEADER,
)
from trialscribe_gateway.utils.enum import ProxyTarget
from trialscribe_gateway.utils.exceptions import UpstreamUnavailableError

router = APIRouter(tags=["gateway"])


def get_gateway_proxy(
    client: Annotated[AsyncClient, Depends(get_http_client)],
    settings: Annotated[GatewaySettings, Depends(get_settings)],
) -> GatewayProxy:
    return GatewayProxy(client, settings)


def get_organization_access_service(
    client: Annotated[AsyncClient, Depends(get_http_client)],
    settings: Annotated[GatewaySettings, Depends(get_settings)],
) -> OrganizationAccessService:
    return OrganizationAccessService(client, settings)


async def _required_account_id(
    token: str | None,
    verifier: AccessTokenVerifier,
    now: datetime,
) -> UUID:
    return await get_current_account_id(token, verifier, now)


def _organization_from_path(path: str) -> UUID | None:
    candidate = path.split("/", maxsplit=1)[0]
    try:
        return UUID(candidate)
    except ValueError:
        return None


async def _require_organization_access(
    organization_header: str | None,
    token: str | None,
    request: Request,
    access: OrganizationAccessService,
) -> UUID:
    if token is None:
        raise authentication_error()
    try:
        organization_id = UUID(organization_header or "")
    except ValueError:
        raise HTTPException(status_code=422, detail=INVALID_ORGANIZATION_DETAIL) from None
    status_code = await access.membership_status(
        token,
        organization_id,
        request.state.request_id,
    )
    if status_code == 200:
        return organization_id
    if status_code == 401:
        raise authentication_error()
    if status_code in {403, 404}:
        raise HTTPException(status_code=403, detail=ORGANIZATION_ACCESS_DENIED_DETAIL)
    raise UpstreamUnavailableError


@router.api_route(
    "/v1/auth/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_auth(
    request: Request,
    path: str,
    token: Annotated[str | None, Depends(get_optional_bearer_token)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    now: Annotated[datetime, Depends(get_now)],
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)],
) -> Response:
    account_id = None
    if not (
        request.method == "POST"
        and path in {"register", "login", "refresh", "logout"}
    ):
        account_id = await _required_account_id(token, verifier, now)
    return await proxy.forward(
        request,
        ProxyTarget.AUTH,
        f"/v1/auth/{path}",
        account_id,
    )


async def _proxy_user_request(
    request: Request,
    upstream_path: str,
    organization_id: UUID | None,
    token: str | None,
    verifier: AccessTokenVerifier,
    now: datetime,
    proxy: GatewayProxy,
) -> Response:
    account_id = await _required_account_id(token, verifier, now)
    return await proxy.forward(
        request,
        ProxyTarget.USER,
        upstream_path,
        account_id,
        organization_id,
    )


@router.api_route(
    "/v1/organizations",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_organizations_root(
    request: Request,
    token: Annotated[str | None, Depends(get_optional_bearer_token)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    now: Annotated[datetime, Depends(get_now)],
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)],
) -> Response:
    return await _proxy_user_request(
        request,
        "/v1/organizations",
        None,
        token,
        verifier,
        now,
        proxy,
    )


@router.api_route(
    "/v1/organizations/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_organizations(
    request: Request,
    path: str,
    token: Annotated[str | None, Depends(get_optional_bearer_token)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    now: Annotated[datetime, Depends(get_now)],
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)],
) -> Response:
    return await _proxy_user_request(
        request,
        f"/v1/organizations/{path}",
        _organization_from_path(path),
        token,
        verifier,
        now,
        proxy,
    )


@router.api_route(
    "/v1/organization-invitations/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_organization_invitations(
    request: Request,
    path: str,
    token: Annotated[str | None, Depends(get_optional_bearer_token)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    now: Annotated[datetime, Depends(get_now)],
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)],
) -> Response:
    return await _proxy_user_request(
        request,
        f"/v1/organization-invitations/{path}",
        None,
        token,
        verifier,
        now,
        proxy,
    )


async def _proxy_organization_capability(
    request: Request,
    target: ProxyTarget,
    upstream_path: str,
    organization_header: str | None,
    token: str | None,
    verifier: AccessTokenVerifier,
    now: datetime,
    access: OrganizationAccessService,
    proxy: GatewayProxy,
) -> Response:
    account_id = await _required_account_id(token, verifier, now)
    organization_id = await _require_organization_access(
        organization_header,
        token,
        request,
        access,
    )
    return await proxy.forward(
        request,
        target,
        upstream_path,
        account_id,
        organization_id,
    )


@router.api_route(
    "/v1/ai/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_ai(
    request: Request,
    path: str,
    organization_header: Annotated[
        str | None,
        Header(alias=ORGANIZATION_ID_HEADER),
    ] = None,
    token: Annotated[str | None, Depends(get_optional_bearer_token)] = None,
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)] = None,
    now: Annotated[datetime, Depends(get_now)] = None,
    access: Annotated[
        OrganizationAccessService,
        Depends(get_organization_access_service),
    ] = None,
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)] = None,
) -> Response:
    return await _proxy_organization_capability(
        request,
        ProxyTarget.AI,
        f"/{path}",
        organization_header,
        token,
        verifier,
        now,
        access,
        proxy,
    )


@router.api_route(
    "/v1/jobs",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_jobs_root(
    request: Request,
    organization_header: Annotated[
        str | None,
        Header(alias=ORGANIZATION_ID_HEADER),
    ] = None,
    token: Annotated[str | None, Depends(get_optional_bearer_token)] = None,
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)] = None,
    now: Annotated[datetime, Depends(get_now)] = None,
    access: Annotated[
        OrganizationAccessService,
        Depends(get_organization_access_service),
    ] = None,
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)] = None,
) -> Response:
    return await _proxy_organization_capability(
        request,
        ProxyTarget.WORKER,
        "/jobs",
        organization_header,
        token,
        verifier,
        now,
        access,
        proxy,
    )


@router.api_route(
    "/v1/jobs/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_jobs(
    request: Request,
    path: str,
    organization_header: Annotated[
        str | None,
        Header(alias=ORGANIZATION_ID_HEADER),
    ] = None,
    token: Annotated[str | None, Depends(get_optional_bearer_token)] = None,
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)] = None,
    now: Annotated[datetime, Depends(get_now)] = None,
    access: Annotated[
        OrganizationAccessService,
        Depends(get_organization_access_service),
    ] = None,
    proxy: Annotated[GatewayProxy, Depends(get_gateway_proxy)] = None,
) -> Response:
    return await _proxy_organization_capability(
        request,
        ProxyTarget.WORKER,
        f"/jobs/{path}",
        organization_header,
        token,
        verifier,
        now,
        access,
        proxy,
    )
