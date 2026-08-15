"""FastAPI assembly for the TrialScribe API gateway."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from trialscribe_observability.http import instrument_app

from trialscribe_gateway.api.routes import router as gateway_router
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.models.health import HealthResponse
from trialscribe_gateway.security.headers import apply_secure_headers
from trialscribe_gateway.security.rate_limit import GatewayRateLimiter
from trialscribe_gateway.utils.constant import (
    APP_TITLE,
    APP_VERSION,
    AUTH_ROUTE_PREFIX,
    CONTENT_SECURITY_POLICY_VALUE,
    DOCS_CONTENT_SECURITY_POLICY_VALUE,
    DOCS_PATHS,
    LIVENESS_STATUS,
    RATE_LIMIT_EXEMPT_PATHS,
    RATE_LIMIT_FAMILY_API,
    RATE_LIMIT_FAMILY_AUTH,
    READINESS_STATUS,
    REQUEST_ID_HEADER,
    RETRY_AFTER_HEADER,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
    TOO_MANY_REQUESTS_DETAIL,
    UPSTREAM_TIMEOUT_DETAIL,
)
from trialscribe_gateway.utils.exceptions import (
    GatewayServiceError,
    RateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)


def _request_id(value: str | None) -> UUID:
    try:
        return UUID(value or "")
    except ValueError:
        return uuid4()


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Create one gateway application with isolated runtime state."""

    cors_origins: list[str] = settings.cors_origins() if settings else []

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or GatewaySettings()
        cors_origins[:] = runtime_settings.cors_origins()
        timeout = httpx.Timeout(
            connect=runtime_settings.gateway_upstream_connect_timeout_seconds,
            read=runtime_settings.gateway_upstream_read_timeout_seconds,
            write=runtime_settings.gateway_upstream_write_timeout_seconds,
            pool=runtime_settings.gateway_upstream_pool_timeout_seconds,
        )
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        application.state.gateway_settings = runtime_settings
        application.state.rate_limiter = GatewayRateLimiter(runtime_settings)
        application.state.http_client = client
        application.state.gateway_ready = True
        try:
            yield
        finally:
            application.state.gateway_ready = False
            await client.aclose()

    application = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan,
    )
    application.include_router(gateway_router)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "X-Organization-ID",
            REQUEST_ID_HEADER,
        ],
        expose_headers=[REQUEST_ID_HEADER],
    )

    def _finalize(request: Request, response: Response) -> Response:
        response.headers[REQUEST_ID_HEADER] = str(request.state.request_id)
        apply_secure_headers(
            response,
            content_security_policy=(
                DOCS_CONTENT_SECURITY_POLICY_VALUE
                if request.url.path in DOCS_PATHS
                else CONTENT_SECURITY_POLICY_VALUE
            ),
        )
        return response

    def _rate_limit(request: Request) -> Response | None:
        if request.method == "OPTIONS" or request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return None
        limiter = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            return None
        family = (
            RATE_LIMIT_FAMILY_AUTH
            if request.url.path.startswith(AUTH_ROUTE_PREFIX)
            else RATE_LIMIT_FAMILY_API
        )
        host = request.client.host if request.client is not None else "unknown"
        try:
            decision = limiter.check(host, family)
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"detail": SERVICE_UNAVAILABLE_DETAIL},
            )
        if decision.allowed:
            return None
        retry_after = decision.retry_after or 1
        return JSONResponse(
            status_code=429,
            content={"detail": TOO_MANY_REQUESTS_DETAIL},
            headers={RETRY_AFTER_HEADER: str(retry_after)},
        )

    @application.middleware("http")
    async def correlation_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = _request_id(request.headers.get(REQUEST_ID_HEADER))
        limited = _rate_limit(request)
        if limited is not None:
            return _finalize(request, limited)
        response = await call_next(request)
        return _finalize(request, response)

    @application.exception_handler(UpstreamUnavailableError)
    async def upstream_unavailable(
        _request: Request,
        _error: UpstreamUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": SERVICE_UNAVAILABLE_DETAIL},
        )

    @application.exception_handler(UpstreamTimeoutError)
    async def upstream_timeout(
        _request: Request,
        _error: UpstreamTimeoutError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=504,
            content={"detail": UPSTREAM_TIMEOUT_DETAIL},
        )

    @application.exception_handler(RateLimitedError)
    async def rate_limited(
        _request: Request,
        error: RateLimitedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": TOO_MANY_REQUESTS_DETAIL},
            headers={RETRY_AFTER_HEADER: str(error.retry_after)},
        )

    @application.exception_handler(GatewayServiceError)
    async def gateway_error(
        _request: Request,
        _error: GatewayServiceError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": SERVICE_UNAVAILABLE_DETAIL},
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        safe_errors = [
            {key: value for key, value in item.items() if key != "input"}
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(safe_errors)},
        )

    @application.get("/health/live", response_model=HealthResponse)
    async def liveness() -> HealthResponse:
        return HealthResponse(
            status=LIVENESS_STATUS,
            service=SERVICE_NAME,
            version=application.version,
        )

    @application.get("/health/ready", response_model=HealthResponse)
    async def readiness(request: Request) -> HealthResponse:
        if not getattr(request.app.state, "gateway_ready", False):
            raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
        return HealthResponse(
            status=READINESS_STATUS,
            service=SERVICE_NAME,
            version=request.app.version,
        )

    instrument_app(application, service=SERVICE_NAME)
    return application


app = create_app()
