"""Requesting, reading, and stopping background work."""

import json
from datetime import datetime
from uuid import UUID, uuid4

from trialscribe_events.contracts.job import JobRequested
from trialscribe_events.registry import EventRegistry
from trialscribe_events.publisher import EventPublisher
from trialscribe_events.utils.constant import (
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
    MAX_JOB_PARAMETERS_BYTES,
)
from trialscribe_events.utils.exceptions import EventPublishError

from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.schemas.job import JobCreateRequest, JobResponse
from trialscribe_worker.utils.constant import SERVICE_NAME
from trialscribe_worker.utils.enum import JobKind, JobStatus
from trialscribe_worker.utils.exceptions import (
    InvalidJobInputError,
    JobAlreadyFinishedError,
    JobNotFoundError,
    JobQueueUnavailableError,
    UnsupportedJobKindError,
)


class JobService:
    """Own the rules a job obeys before, during, and after the queue."""

    def __init__(
        self,
        jobs: JobRepository,
        progress: JobProgressStore,
        publisher: EventPublisher,
        registry: EventRegistry,
    ) -> None:
        self._jobs = jobs
        self._progress = progress
        self._publisher = publisher
        self._registry = registry

    async def request_job(
        self,
        organization_id: UUID,
        account_id: UUID,
        request: JobCreateRequest,
        now: datetime,
    ) -> JobResponse:
        """Record a job and hand it to the queue before the caller's write lands.

        The queue message is sent while the transaction is still open, so a broker
        that cannot take it undoes the ticket too. That order is deliberate: a
        rejected request is recoverable, a ticket nobody will ever work on is not.
        """

        kind = self._validate_kind(request.kind)
        parameters = self._validate_parameters(request.parameters)
        job = await self._jobs.add(
            Job(
                organization_id=organization_id,
                conversation_id=request.conversation_id,
                requested_by_account_id=account_id,
                correlation_id=uuid4(),
                kind=kind.value,
                status=JobStatus.QUEUED.value,
                attempt=0,
                progress=0,
                parameters=parameters,
            )
        )
        await self._publish(job, now)
        return self._response(job, None)

    async def get_job(self, organization_id: UUID, job_id: UUID) -> JobResponse:
        """Return one job, with the higher of its live and durable progress."""

        job = await self._jobs.get(organization_id, job_id)
        if job is None:
            raise JobNotFoundError
        return self._response(job, await self._progress.get_progress(job_id))

    async def cancel_job(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> JobResponse:
        """Stop a job outright if it never started, or ask it to stop if it did."""

        cancelled = await self._jobs.cancel_queued(organization_id, job_id, now)
        if cancelled is not None:
            await self._progress.clear(job_id)
            return self._response(cancelled, None)

        requested = await self._jobs.request_cancel(organization_id, job_id, now)
        if requested is None:
            raise await self._absent_or_finished(organization_id, job_id)
        await self._progress.request_cancel(job_id)
        return self._response(requested, await self._progress.get_progress(job_id))

    async def _absent_or_finished(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> Exception:
        existing = await self._jobs.get(organization_id, job_id)
        if existing is None:
            return JobNotFoundError()
        return JobAlreadyFinishedError()

    def _validate_kind(self, kind: str) -> JobKind:
        try:
            return JobKind(kind)
        except ValueError:
            raise UnsupportedJobKindError from None

    def _validate_parameters(self, parameters: dict[str, object]) -> dict[str, object]:
        try:
            encoded = json.dumps(parameters).encode("utf-8")
        except (TypeError, ValueError):
            raise InvalidJobInputError from None
        if len(encoded) > MAX_JOB_PARAMETERS_BYTES:
            raise InvalidJobInputError
        return parameters

    async def _publish(self, job: Job, now: datetime) -> None:
        envelope = self._registry.build(
            event_type=JOB_REQUESTED_EVENT_TYPE,
            version=JOB_EVENT_VERSION,
            organization_id=job.organization_id,
            subject=str(job.id),
            correlation_id=job.correlation_id,
            producer=SERVICE_NAME,
            occurred_at=now,
            payload=JobRequested(
                job_id=job.id,
                kind=job.kind,
                organization_id=job.organization_id,
                conversation_id=job.conversation_id,
                requested_by_account_id=job.requested_by_account_id,
                attempt=1,
                parameters=job.parameters,
            ),
        )
        try:
            await self._publisher.publish(envelope)
        except EventPublishError:
            raise JobQueueUnavailableError from None

    def _response(self, job: Job, live_progress: int | None) -> JobResponse:
        return JobResponse(
            id=job.id,
            organization_id=job.organization_id,
            conversation_id=job.conversation_id,
            kind=job.kind,
            status=JobStatus(job.status),
            progress=max(job.progress, live_progress or 0),
            attempt=job.attempt,
            error_code=job.error_code,
            correlation_id=job.correlation_id,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            cancel_requested_at=job.cancel_requested_at,
        )
