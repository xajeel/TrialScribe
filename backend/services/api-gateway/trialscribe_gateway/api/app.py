"""FastAPI assembly for the TrialScribe API gateway."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from trialscribe_observability.http import instrument_app

from trialscribe_gateway.api.routes import router as gateway_router
from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.models.health import HealthResponse
from trialscribe_gateway.utils.constant import (
    APP_TITLE,
    APP_VERSION,
    LIVENESS_STATUS,
    READINESS_STATUS,
    REQUEST_ID_HEADER,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
    UPSTREAM_TIMEOUT_DETAIL,
)
from trialscribe_gateway.utils.exceptions import (
    GatewayServiceError,
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

    @application.middleware("http")
    async def correlation_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = _request_id(request.headers.get(REQUEST_ID_HEADER))
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = str(request.state.request_id)
        return response

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

    @application.exception_handler(GatewayServiceError)
    async def gateway_error(
        _request: Request,
        _error: GatewayServiceError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": SERVICE_UNAVAILABLE_DETAIL},
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
