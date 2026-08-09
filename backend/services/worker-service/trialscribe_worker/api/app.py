"""The worker's HTTP boundary: accept work, report on it, stop it."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.contracts.job import register_job_events
from trialscribe_events.publisher import create_event_publisher
from trialscribe_events.registry import EventRegistry

from trialscribe_worker.api.jobs import router as job_router
from trialscribe_worker.config import WorkerRedisSettings, WorkerSettings
from trialscribe_worker.models.health import HealthResponse
from trialscribe_worker.utils.constant import (
    APP_TITLE,
    APP_VERSION,
    INVALID_JOB_INPUT_DETAIL,
    JOB_ALREADY_FINISHED_DETAIL,
    JOB_NOT_FOUND_DETAIL,
    JOB_QUEUE_UNAVAILABLE_DETAIL,
    LIVENESS_STATUS,
    READINESS_STATUS,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
    UNSUPPORTED_JOB_KIND_DETAIL,
)
from trialscribe_worker.utils.exceptions import (
    InvalidJobInputError,
    JobAlreadyFinishedError,
    JobNotFoundError,
    JobQueueUnavailableError,
    UnsupportedJobKindError,
    WorkerServiceError,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own the database, Redis, and queue connections for the boundary's life."""

    worker_settings = WorkerSettings()
    event_settings = EventBusSettings(consumer_group=worker_settings.consumer_group)
    registry = register_job_events(EventRegistry())
    publisher = create_event_publisher(event_settings, registry)

    application.state.worker_settings = worker_settings
    application.state.event_settings = event_settings
    application.state.event_registry = registry
    application.state.event_publisher = publisher
    application.state.database_runtime = create_database_runtime(DatabaseSettings())
    application.state.redis = Redis.from_url(
        WorkerRedisSettings().connection_url(),
        decode_responses=False,
    )

    await publisher.start()
    try:
        yield
    finally:
        await publisher.stop()
        await application.state.redis.aclose()
        await application.state.database_runtime.dispose()


app: FastAPI = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
app.include_router(job_router)


@app.exception_handler(WorkerServiceError)
async def worker_error_response(
    _request: Request,
    error: WorkerServiceError,
) -> JSONResponse:
    """Translate expected failures into fixed messages, never exception text."""

    if isinstance(error, JobNotFoundError):
        status_code, detail = 404, JOB_NOT_FOUND_DETAIL
    elif isinstance(error, JobAlreadyFinishedError):
        status_code, detail = 409, JOB_ALREADY_FINISHED_DETAIL
    elif isinstance(error, UnsupportedJobKindError):
        status_code, detail = 422, UNSUPPORTED_JOB_KIND_DETAIL
    elif isinstance(error, InvalidJobInputError):
        status_code, detail = 422, INVALID_JOB_INPUT_DETAIL
    elif isinstance(error, JobQueueUnavailableError):
        status_code, detail = 503, JOB_QUEUE_UNAVAILABLE_DETAIL
    else:
        status_code, detail = 503, SERVICE_UNAVAILABLE_DETAIL
    return JSONResponse(status_code=status_code, content={"detail": detail})


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
            raise RuntimeError
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
