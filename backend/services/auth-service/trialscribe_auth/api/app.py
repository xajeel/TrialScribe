from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_auth.api.routes import router as auth_router
from trialscribe_auth.config import AuthSettings
from trialscribe_auth.models.health import HealthResponse
from trialscribe_auth.utils.constant import (
    APP_TITLE,
    APP_VERSION,
    LIVENESS_STATUS,
    READINESS_STATUS,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
)
from trialscribe_auth.utils.exceptions import DependencyUnavailableError


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = AuthSettings()
    database_runtime = create_database_runtime(DatabaseSettings())
    redis = Redis.from_url(settings.redis_connection_url())
    application.state.auth_settings = settings
    application.state.database_runtime = database_runtime
    application.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await database_runtime.dispose()


app: FastAPI = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    lifespan=lifespan,
)
app.include_router(auth_router)


@app.exception_handler(RequestValidationError)
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


@app.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status=LIVENESS_STATUS,
        service=SERVICE_NAME,
        version=app.version,
    )


@app.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse:
    try:
        async with request.app.state.database_runtime.transaction() as session:
            await session.execute(text("SELECT 1"))
        if not await request.app.state.redis.ping():
            raise DependencyUnavailableError("Redis ping failed")
    except Exception:
        raise HTTPException(
            status_code=503,
            detail=SERVICE_UNAVAILABLE_DETAIL,
        ) from None
    return HealthResponse(
        status=READINESS_STATUS,
        service=SERVICE_NAME,
        version=request.app.version,
    )
