from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_auth.api.routes import router as auth_router
from trialscribe_auth.config import AuthSettings
from trialscribe_auth.models.health import HealthResponse


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
    title="TrialScribe Auth",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(auth_router)


@app.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok", service="auth-service", version=app.version)


@app.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse:
    try:
        async with request.app.state.database_runtime.transaction() as session:
            await session.execute(text("SELECT 1"))
        if not await request.app.state.redis.ping():
            raise RuntimeError("Redis ping failed")
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable") from None
    return HealthResponse(
        status="ready",
        service="auth-service",
        version=request.app.version,
    )
