"""FastAPI dependencies for gateway runtime resources and identity."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from httpx import AsyncClient

from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.security.tokens import AccessTokenVerifier
from trialscribe_gateway.utils.constant import INVALID_AUTHENTICATION_DETAIL
from trialscribe_gateway.utils.exceptions import InvalidAccessTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


def get_settings(request: Request) -> GatewaySettings:
    return request.app.state.gateway_settings


def get_http_client(request: Request) -> AsyncClient:
    return request.app.state.http_client


def get_token_verifier(
    settings: Annotated[GatewaySettings, Depends(get_settings)],
) -> AccessTokenVerifier:
    return AccessTokenVerifier(settings)


def get_now() -> datetime:
    return datetime.now(UTC)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=INVALID_AUTHENTICATION_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_bearer_token(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> str | None:
    return token


async def get_current_account_id(
    token: Annotated[str | None, Depends(get_optional_bearer_token)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    now: Annotated[datetime, Depends(get_now)],
) -> UUID:
    if token is None:
        raise authentication_error()
    try:
        return verifier.decode_access_token(token, now).sub
    except InvalidAccessTokenError:
        raise authentication_error() from None
