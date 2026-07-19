"""FastAPI dependencies for user-service runtime resources."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_user.config import UserSettings
from trialscribe_user.security.tokens import (
    AccessTokenVerifier,
    InvalidAccessTokenError,
)
from trialscribe_user.utils.constant import INVALID_AUTHENTICATION_DETAIL

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


def get_settings(request: Request) -> UserSettings:
    return request.app.state.user_settings


def get_database_runtime(request: Request) -> DatabaseRuntime:
    return request.app.state.database_runtime


def get_token_verifier(
    settings: Annotated[UserSettings, Depends(get_settings)],
) -> AccessTokenVerifier:
    return AccessTokenVerifier(settings)


def get_now() -> datetime:
    return datetime.now(UTC)


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=INVALID_AUTHENTICATION_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_account_id(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    now: Annotated[datetime, Depends(get_now)],
) -> UUID:
    if token is None:
        raise _authentication_error()
    try:
        return verifier.decode_access_token(token, now).sub
    except InvalidAccessTokenError:
        raise _authentication_error() from None
