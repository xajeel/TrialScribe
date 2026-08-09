"""HTTP routes for requesting, reading, and stopping background work."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime
from trialscribe_events.publisher import EventPublisher
from trialscribe_events.registry import EventRegistry

from trialscribe_worker.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
    get_progress_store,
    get_publisher,
    get_registry,
)
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.schemas.job import JobCreateRequest, JobResponse
from trialscribe_worker.services.jobs import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])

AccountId = Annotated[UUID, Depends(get_current_account_id)]
OrganizationId = Annotated[UUID, Depends(get_current_organization_id)]
Runtime = Annotated[DatabaseRuntime, Depends(get_database_runtime)]
Progress = Annotated[JobProgressStore, Depends(get_progress_store)]
Publisher = Annotated[EventPublisher, Depends(get_publisher)]
Registry = Annotated[EventRegistry, Depends(get_registry)]
Now = Annotated[datetime, Depends(get_now)]


def _service(
    session: AsyncSession,
    progress: JobProgressStore,
    publisher: EventPublisher,
    registry: EventRegistry,
) -> JobService:
    return JobService(JobRepository(session), progress, publisher, registry)


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_job(
    body: JobCreateRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    publisher: Publisher,
    registry: Registry,
    now: Now,
) -> JobResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, publisher, registry)
        return await service.request_job(organization_id, account_id, body, now)


@router.get("/{job_id}", response_model=JobResponse)
async def read_job(
    job_id: UUID,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    publisher: Publisher,
    registry: Registry,
) -> JobResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, publisher, registry)
        return await service.get_job(organization_id, job_id)


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_job(
    job_id: UUID,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    publisher: Publisher,
    registry: Registry,
    now: Now,
) -> JobResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, publisher, registry)
        return await service.cancel_job(organization_id, job_id, now)
