"""FastAPI dependencies for trusted worker runtime context."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, Request

from trialscribe_db.runtime import DatabaseRuntime
from trialscribe_events.publisher import EventPublisher
from trialscribe_events.registry import EventRegistry

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.repositories.job_progress import (
    JobProgressStore,
    KeyValueStore,
)
from trialscribe_worker.utils.constant import (
    INTERNAL_ACCOUNT_ID_HEADER,
    INTERNAL_ORGANIZATION_ID_HEADER,
    INVALID_ACCOUNT_CONTEXT_DETAIL,
    INVALID_ORGANIZATION_CONTEXT_DETAIL,
)


def get_database_runtime(request: Request) -> DatabaseRuntime:
    return request.app.state.database_runtime


def get_redis(request: Request) -> KeyValueStore:
    return request.app.state.redis


def get_settings(request: Request) -> WorkerSettings:
    return request.app.state.worker_settings


def get_publisher(request: Request) -> EventPublisher:
    return request.app.state.event_publisher


def get_registry(request: Request) -> EventRegistry:
    return request.app.state.event_registry


def get_progress_store(request: Request) -> JobProgressStore:
    return JobProgressStore(
        get_redis(request),
        get_settings(request).progress_ttl_seconds,
    )


def get_now() -> datetime:
    return datetime.now(UTC)


def get_current_account_id(
    value: Annotated[
        str | None,
        Header(alias=INTERNAL_ACCOUNT_ID_HEADER),
    ] = None,
) -> UUID:
    if value is None:
        raise HTTPException(status_code=401, detail=INVALID_ACCOUNT_CONTEXT_DETAIL)
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=INVALID_ACCOUNT_CONTEXT_DETAIL,
        ) from None


def get_current_organization_id(
    value: Annotated[
        str | None,
        Header(alias=INTERNAL_ORGANIZATION_ID_HEADER),
    ] = None,
) -> UUID:
    if value is None:
        raise HTTPException(
            status_code=422,
            detail=INVALID_ORGANIZATION_CONTEXT_DETAIL,
        )
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=INVALID_ORGANIZATION_CONTEXT_DETAIL,
        ) from None
