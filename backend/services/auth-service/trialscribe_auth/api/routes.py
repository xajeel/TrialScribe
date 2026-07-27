"""Versioned HTTP routes for local account authentication."""

from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_auth.api.dependencies import (
    get_bearer_token,
    get_database_runtime,
    get_now,
    get_rate_limiter,
    get_settings,
    get_token_codec,
)
from trialscribe_auth.config import AuthSettings
from trialscribe_auth.repositories.accounts import AccountRepository
from trialscribe_auth.repositories.sessions import SessionRepository
from trialscribe_auth.schemas.account import AccountResponse, RegisterRequest
from trialscribe_auth.schemas.auth import LoginRequest, TokenResponse
from trialscribe_auth.security.passwords import dummy_verify, verify_password
from trialscribe_auth.security.rate_limit import (
    LoginRateLimiter,
    RateLimitUnavailableError,
)
from trialscribe_auth.security.tokens import AccessTokenCodec, InvalidAccessTokenError
from trialscribe_auth.services.accounts import (
    AccountConflictError,
    AccountService,
    InvalidAccountInput,
    normalize_email,
)
from trialscribe_auth.services.sessions import SessionCredentials, SessionService
from trialscribe_auth.utils.constant import (
    ACCOUNT_CONFLICT_DETAIL,
    AUTH_COOKIE_PATH,
    AUTHENTICATION_UNAVAILABLE_DETAIL,
    CSRF_COOKIE,
    CSRF_COOKIE_PATH,
    INVALID_ACCOUNT_DETAIL,
    INVALID_AUTHENTICATION_DETAIL,
    REFRESH_COOKIE,
    TOO_MANY_ATTEMPTS_DETAIL,
)

router = APIRouter(prefix="/v1/auth", tags=["authentication"])


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=INVALID_AUTHENTICATION_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _set_session_cookies(
    response: Response,
    credentials: SessionCredentials,
    settings: AuthSettings,
    now: datetime,
) -> None:
    max_age = max(int((credentials.expires_at - now).total_seconds()), 0)
    shared = {
        "secure": settings.auth_cookie_secure,
        "samesite": "strict",
        "max_age": max_age,
    }
    response.set_cookie(
        REFRESH_COOKIE,
        credentials.refresh_token,
        httponly=True,
        path=AUTH_COOKIE_PATH,
        **shared,
    )
    response.set_cookie(
        CSRF_COOKIE,
        credentials.csrf_token,
        httponly=False,
        path=CSRF_COOKIE_PATH,
        **shared,
    )


def _clear_session_cookies(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=AUTH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path=CSRF_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite="strict",
    )


def _rejected_cookie_response(settings: AuthSettings) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": INVALID_AUTHENTICATION_DETAIL},
        headers={"WWW-Authenticate": "Bearer"},
    )
    _clear_session_cookies(response, settings)
    return response


def _token_response(
    codec: AccessTokenCodec,
    credentials: SessionCredentials,
    settings: AuthSettings,
    now: datetime,
) -> TokenResponse:
    return TokenResponse(
        access_token=codec.issue_access_token(credentials.account_id, now),
        expires_in=settings.auth_access_token_ttl_seconds,
    )


@router.post("/register", response_model=AccountResponse, status_code=201)
async def register(
    body: RegisterRequest,
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> AccountResponse:
    try:
        async with database.transaction() as session:
            account = await AccountService(AccountRepository(session)).register_account(
                body.email,
                body.password,
            )
    except AccountConflictError:
        raise HTTPException(status_code=409, detail=ACCOUNT_CONFLICT_DETAIL) from None
    except InvalidAccountInput:
        raise HTTPException(status_code=422, detail=INVALID_ACCOUNT_DETAIL) from None
    return AccountResponse.model_validate(account)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[AuthSettings, Depends(get_settings)],
    codec: Annotated[AccessTokenCodec, Depends(get_token_codec)],
    limiter: Annotated[LoginRateLimiter, Depends(get_rate_limiter)],
    now: Annotated[datetime, Depends(get_now)],
) -> TokenResponse:
    peer_address = request.client.host if request.client is not None else "unknown"
    try:
        normalized_email = normalize_email(body.email)
    except InvalidAccountInput:
        normalized_email = body.email.strip().casefold()

    async with database.transaction() as session:
        account = await AccountRepository(session).get_by_email(normalized_email)
        if account is None:
            dummy_verify(body.password)
            valid_credentials = False
        else:
            valid_credentials = verify_password(body.password, account.password_hash)
            valid_credentials = valid_credentials and account.is_active

        if not valid_credentials:
            try:
                decision = await limiter.record_failure(normalized_email, peer_address)
            except RateLimitUnavailableError:
                raise HTTPException(
                    status_code=503,
                    detail=AUTHENTICATION_UNAVAILABLE_DETAIL,
                ) from None
            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail=TOO_MANY_ATTEMPTS_DETAIL,
                    headers={"Retry-After": str(decision.retry_after)},
                )
            raise _authentication_error()

        try:
            await limiter.clear_success(normalized_email, peer_address)
        except RateLimitUnavailableError:
            raise HTTPException(
                status_code=503,
                detail=AUTHENTICATION_UNAVAILABLE_DETAIL,
            ) from None
        credentials = await SessionService(
            SessionRepository(session),
            settings,
        ).create_session(account.id, now)

    _set_session_cookies(response, credentials, settings, now)
    return _token_response(codec, credentials, settings, now)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[AuthSettings, Depends(get_settings)],
    codec: Annotated[AccessTokenCodec, Depends(get_token_codec)],
    now: Annotated[datetime, Depends(get_now)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> TokenResponse | Response:
    if not refresh_token or not csrf_cookie or not csrf_header:
        return _rejected_cookie_response(settings)
    async with database.transaction() as session:
        session_service = SessionService(SessionRepository(session), settings)
        result = await session_service.rotate_session(
            refresh_token,
            csrf_cookie,
            csrf_header,
            now,
        )
        credentials = result.credentials
        if credentials is not None:
            account = await AccountRepository(session).get_by_id(credentials.account_id)
            if account is None or not account.is_active:
                await session_service.revoke_all(credentials.account_id, now)
                credentials = None
    if credentials is None:
        return _rejected_cookie_response(settings)

    response = JSONResponse(
        content=_token_response(codec, credentials, settings, now).model_dump()
    )
    _set_session_cookies(response, credentials, settings, now)
    return response


@router.post("/logout", status_code=204)
async def logout(
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[AuthSettings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Response:
    if not refresh_token or not csrf_cookie or not csrf_header:
        return _rejected_cookie_response(settings)
    async with database.transaction() as session:
        revoked = await SessionService(
            SessionRepository(session),
            settings,
        ).revoke_current(refresh_token, csrf_cookie, csrf_header, now)
    if not revoked:
        return _rejected_cookie_response(settings)
    response = Response(status_code=204)
    _clear_session_cookies(response, settings)
    return response


async def _active_account(
    token: str,
    codec: AccessTokenCodec,
    database: DatabaseRuntime,
    now: datetime,
) -> AccountResponse:
    try:
        claims = codec.decode_access_token(token, now)
    except InvalidAccessTokenError:
        raise _authentication_error() from None
    async with database.transaction() as session:
        account = await AccountRepository(session).get_by_id(claims.sub)
    if account is None or not account.is_active:
        raise _authentication_error()
    return AccountResponse.model_validate(account)


@router.get("/me", response_model=AccountResponse)
async def current_account(
    token: Annotated[str, Depends(get_bearer_token)],
    codec: Annotated[AccessTokenCodec, Depends(get_token_codec)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    now: Annotated[datetime, Depends(get_now)],
) -> AccountResponse:
    return await _active_account(token, codec, database, now)


@router.post("/logout-all", status_code=204)
async def logout_all(
    token: Annotated[str, Depends(get_bearer_token)],
    codec: Annotated[AccessTokenCodec, Depends(get_token_codec)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[AuthSettings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    account = await _active_account(token, codec, database, now)
    async with database.transaction() as session:
        await SessionService(SessionRepository(session), settings).revoke_all(
            account.id,
            now,
        )
    response = Response(status_code=204)
    _clear_session_cookies(response, settings)
    return response
