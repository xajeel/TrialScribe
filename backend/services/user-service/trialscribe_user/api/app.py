from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime
from trialscribe_observability.http import instrument_app

from trialscribe_user.api.routes import router as organization_router
from trialscribe_user.config import UserSettings
from trialscribe_user.models.health import HealthResponse
from trialscribe_user.utils.constant import (
    APP_TITLE,
    APP_VERSION,
    LIVENESS_STATUS,
    READINESS_STATUS,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.user_settings = UserSettings()
    application.state.database_runtime = create_database_runtime(DatabaseSettings())
    try:
        yield
    finally:
        await application.state.database_runtime.dispose()


app: FastAPI = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    lifespan=lifespan,
)
app.include_router(organization_router)


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


instrument_app(app, service=SERVICE_NAME)
