"""HTTP routes for requesting, reading, and stopping background work."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.logs import event_context, get_event_logger
from trialscribe_events.outbox_relay import OutboxRelay
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.outbox import OutboxRepository

from trialscribe_worker.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_event_settings,
    get_now,
    get_outbox_relay,
    get_progress_store,
    get_registry,
)
from trialscribe_worker.repositories.generation_outcomes import GenerationOutcomeRepository
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.repositories.provider_calls import ProviderCallRepository
from trialscribe_worker.schemas.job import (
    GenerationAttemptListResponse,
    GenerationAttemptPublic,
    JobCreateRequest,
    JobListResponse,
    JobResponse,
    RewriteOptionListResponse,
    RewriteOptionPublic,
    UsageResponse,
)
from trialscribe_worker.services.jobs import JobService
from trialscribe_worker.services.usage import build_usage_view
from trialscribe_worker.utils.constant import (
    CONVERSATION_NOT_FOUND_DETAIL,
    JOB_LIST_DEFAULT_LIMIT,
    JOB_LIST_MAX_LIMIT,
    JOB_LIST_MIN_LIMIT,
)

logger = get_event_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

AccountId = Annotated[UUID, Depends(get_current_account_id)]
OrganizationId = Annotated[UUID, Depends(get_current_organization_id)]
Runtime = Annotated[DatabaseRuntime, Depends(get_database_runtime)]
Progress = Annotated[JobProgressStore, Depends(get_progress_store)]
Registry = Annotated[EventRegistry, Depends(get_registry)]
EventSettings = Annotated[EventBusSettings, Depends(get_event_settings)]
Relay = Annotated[OutboxRelay, Depends(get_outbox_relay)]
Now = Annotated[datetime, Depends(get_now)]


def _service(
    session: AsyncSession,
    progress: JobProgressStore,
    registry: EventRegistry,
    topic_prefix: str,
) -> JobService:
    return JobService(
        JobRepository(session),
        progress,
        OutboxRepository(session),
        registry,
        topic_prefix,
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_job(
    body: JobCreateRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    registry: Registry,
    event_settings: EventSettings,
    relay: Relay,
    now: Now,
) -> JobResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, registry, event_settings.topic_prefix)
        response = await service.request_job(organization_id, account_id, body, now)

    await _hand_over_promptly(relay)
    return response


async def _hand_over_promptly(relay: OutboxRelay) -> None:
    """Push the job onto the queue now, rather than waiting for the next sweep.

    The ticket and its queue message are already committed together, so the job
    is safely queued whether or not this succeeds. This only shortens the wait on
    a healthy system; a failure is the relay's problem, never the caller's.
    """

    try:
        await relay.drain_once()
    except Exception:
        logger.warning(
            "job.inline_handover_failed",
            extra={"event_context": event_context(reason="relay_unavailable")},
        )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    conversation_id: UUID,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    registry: Registry,
    event_settings: EventSettings,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=JOB_LIST_MIN_LIMIT, le=JOB_LIST_MAX_LIMIT)] = (
        JOB_LIST_DEFAULT_LIMIT
    ),
) -> JobListResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, registry, event_settings.topic_prefix)
        return await service.list_jobs(organization_id, conversation_id, kind, limit)


@router.get("/{job_id}/attempts", response_model=GenerationAttemptListResponse)
async def list_job_attempts(
    job_id: UUID,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    registry: Registry,
    event_settings: EventSettings,
) -> GenerationAttemptListResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, registry, event_settings.topic_prefix)
        job = await service.get_job(organization_id, job_id)
        if job.conversation_id is None:
            return GenerationAttemptListResponse(items=[])
        rows = await GenerationOutcomeRepository(session).list_latest_for_job(
            organization_id,
            job.conversation_id,
            job_id,
        )
    return GenerationAttemptListResponse(
        items=[
            GenerationAttemptPublic(
                section_number=row.section_number,
                status=row.status,
                error_code=row.error_code,
                citation_ids=row.citation_ids,
                attempt=row.attempt,
            )
            for row in rows
        ]
    )


@router.get("/{job_id}/rewrite-options", response_model=RewriteOptionListResponse)
async def list_rewrite_options(
    job_id: UUID,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    registry: Registry,
    event_settings: EventSettings,
) -> RewriteOptionListResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, registry, event_settings.topic_prefix)
        job = await service.get_job(organization_id, job_id)
        if job.conversation_id is None:
            return RewriteOptionListResponse(items=[])
        rows = await GenerationOutcomeRepository(session).get_rewrite_options(
            organization_id,
            job.conversation_id,
            job_id,
        )
    return RewriteOptionListResponse(
        items=[RewriteOptionPublic(id=option_id, text=text) for option_id, text in rows]
    )


@router.get("/usage", response_model=UsageResponse)
async def read_usage(
    organization_id: OrganizationId,
    account_id: AccountId,
    runtime: Runtime,
    conversation_id: Annotated[UUID, Query()],
) -> UsageResponse:
    async with runtime.transaction() as session:
        calls = ProviderCallRepository(session)
        jobs = JobRepository(session)
        conversation = await calls.get_conversation(organization_id, conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=CONVERSATION_NOT_FOUND_DETAIL,
            )
        title, _activity = conversation
        totals = await calls.summarize_conversation(organization_id, conversation_id)
        records = await calls.list_for_conversation(organization_id, conversation_id)
        job_ids = list(
            dict.fromkeys(record.job_id for record in records if record.job_id is not None)
        )
        loaded = await jobs.list_usage_jobs(organization_id, conversation_id, job_ids)
        in_flight = await jobs.list_in_flight_usage_jobs(
            organization_id,
            conversation_id,
        )
        merged = list(loaded)
        seen = {job.id for job in merged}
        for job in in_flight:
            if job.id not in seen:
                merged.append(job)
                seen.add(job.id)
        view = build_usage_view(
            protocol_title=title,
            protocol_id=conversation_id,
            viewer_account_id=account_id,
            jobs=merged,
            calls=records,
            summary=totals,
        )
    return UsageResponse.model_validate(view)


@router.get("/{job_id}", response_model=JobResponse)
async def read_job(
    job_id: UUID,
    organization_id: OrganizationId,
    runtime: Runtime,
    progress: Progress,
    registry: Registry,
    event_settings: EventSettings,
) -> JobResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, registry, event_settings.topic_prefix)
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
    registry: Registry,
    event_settings: EventSettings,
    now: Now,
) -> JobResponse:
    async with runtime.transaction() as session:
        service = _service(session, progress, registry, event_settings.topic_prefix)
        return await service.cancel_job(organization_id, job_id, now)
