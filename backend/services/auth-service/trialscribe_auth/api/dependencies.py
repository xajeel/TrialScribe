"""FastAPI dependencies for authentication runtime resources."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.security.rate_limit import LoginRateLimiter
from trialscribe_auth.security.tokens import AccessTokenCodec
from trialscribe_auth.utils.constant import INVALID_AUTHENTICATION_DETAIL

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


def get_settings(request: Request) -> AuthSettings:
    return request.app.state.auth_settings


def get_database_runtime(request: Request) -> DatabaseRuntime:
    return request.app.state.database_runtime


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_token_codec(
    settings: Annotated[AuthSettings, Depends(get_settings)],
) -> AccessTokenCodec:
    return AccessTokenCodec(settings)


def get_rate_limiter(
    backend: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[AuthSettings, Depends(get_settings)],
) -> LoginRateLimiter:
    return LoginRateLimiter(backend, settings)


def get_now() -> datetime:
    return datetime.now(UTC)


async def get_bearer_token(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> str:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_AUTHENTICATION_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token
