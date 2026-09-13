"""Versioned reverse-proxy routes for backend service boundaries.

Every route does the same three things in the same order: prove who is calling,
prove what they may reach, then forward the request untouched. Those three steps
live in `_forward_authenticated` and `_forward_with_organization`; each route
below only names its upstream and its path.
"""

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
    PROXY_METHODS,
    PUBLIC_AUTH_PATHS,
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


Token = Annotated[str | None, Depends(get_optional_bearer_token)]
Verifier = Annotated[AccessTokenVerifier, Depends(get_token_verifier)]
Now = Annotated[datetime, Depends(get_now)]
Proxy = Annotated[GatewayProxy, Depends(get_gateway_proxy)]
Access = Annotated[
    OrganizationAccessService,
    Depends(get_organization_access_service),
]
OrganizationHeader = Annotated[str | None, Header(alias=ORGANIZATION_ID_HEADER)]


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
    """Confirm the caller still belongs to the organization they named.

    Membership is read from user-service on every protected request rather than
    trusted from the token, so a revoked membership stops working immediately.
    """

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


async def _forward_authenticated(
    request: Request,
    target: ProxyTarget,
    upstream_path: str,
    *,
    token: str | None,
    verifier: AccessTokenVerifier,
    now: datetime,
    proxy: GatewayProxy,
    organization_id: UUID | None = None,
) -> Response:
    """Forward on behalf of a proven account, without an organization check."""

    account_id = await _required_account_id(token, verifier, now)
    return await proxy.forward(
        request,
        target,
        upstream_path,
        account_id,
        organization_id,
    )


async def _forward_with_organization(
    request: Request,
    target: ProxyTarget,
    upstream_path: str,
    *,
    organization_header: str | None,
    token: str | None,
    verifier: AccessTokenVerifier,
    now: datetime,
    access: OrganizationAccessService,
    proxy: GatewayProxy,
) -> Response:
    """Forward only after both the account and its membership are proven."""

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


@router.api_route("/v1/auth/{path:path}", methods=PROXY_METHODS)
async def proxy_auth(
    request: Request,
    path: str,
    token: Token,
    verifier: Verifier,
    now: Now,
    proxy: Proxy,
) -> Response:
    """Forward authentication traffic, leaving the public entry points open."""

    account_id = None
    if not (request.method == "POST" and path in PUBLIC_AUTH_PATHS):
        account_id = await _required_account_id(token, verifier, now)
    return await proxy.forward(request, ProxyTarget.AUTH, f"/v1/auth/{path}", account_id)


@router.api_route("/v1/organizations", methods=PROXY_METHODS)
async def proxy_organizations_root(
    request: Request,
    token: Token,
    verifier: Verifier,
    now: Now,
    proxy: Proxy,
) -> Response:
    return await _forward_authenticated(
        request,
        ProxyTarget.USER,
        "/v1/organizations",
        token=token,
        verifier=verifier,
        now=now,
        proxy=proxy,
    )


@router.api_route("/v1/organizations/{path:path}", methods=PROXY_METHODS)
async def proxy_organizations(
    request: Request,
    path: str,
    token: Token,
    verifier: Verifier,
    now: Now,
    proxy: Proxy,
) -> Response:
    return await _forward_authenticated(
        request,
        ProxyTarget.USER,
        f"/v1/organizations/{path}",
        token=token,
        verifier=verifier,
        now=now,
        proxy=proxy,
        organization_id=_organization_from_path(path),
    )


@router.api_route("/v1/organization-invitations/{path:path}", methods=PROXY_METHODS)
async def proxy_organization_invitations(
    request: Request,
    path: str,
    token: Token,
    verifier: Verifier,
    now: Now,
    proxy: Proxy,
) -> Response:
    return await _forward_authenticated(
        request,
        ProxyTarget.USER,
        f"/v1/organization-invitations/{path}",
        token=token,
        verifier=verifier,
        now=now,
        proxy=proxy,
    )


@router.api_route("/v1/ai/{path:path}", methods=PROXY_METHODS)
async def proxy_ai(
    request: Request,
    path: str,
    token: Token,
    verifier: Verifier,
    now: Now,
    access: Access,
    proxy: Proxy,
    organization_header: OrganizationHeader = None,
) -> Response:
    return await _forward_with_organization(
        request,
        ProxyTarget.AI,
        f"/{path}",
        organization_header=organization_header,
        token=token,
        verifier=verifier,
        now=now,
        access=access,
        proxy=proxy,
    )


@router.api_route("/v1/jobs", methods=PROXY_METHODS)
async def proxy_jobs_root(
    request: Request,
    token: Token,
    verifier: Verifier,
    now: Now,
    access: Access,
    proxy: Proxy,
    organization_header: OrganizationHeader = None,
) -> Response:
    return await _forward_with_organization(
        request,
        ProxyTarget.WORKER,
        "/jobs",
        organization_header=organization_header,
        token=token,
        verifier=verifier,
        now=now,
        access=access,
        proxy=proxy,
    )


@router.api_route("/v1/jobs/{path:path}", methods=PROXY_METHODS)
async def proxy_jobs(
    request: Request,
    path: str,
    token: Token,
    verifier: Verifier,
    now: Now,
    access: Access,
    proxy: Proxy,
    organization_header: OrganizationHeader = None,
) -> Response:
    return await _forward_with_organization(
        request,
        ProxyTarget.WORKER,
        f"/jobs/{path}",
        organization_header=organization_header,
        token=token,
        verifier=verifier,
        now=now,
        access=access,
        proxy=proxy,
    )
