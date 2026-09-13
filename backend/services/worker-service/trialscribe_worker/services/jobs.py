"""Requesting, reading, and stopping background work."""

import json
from datetime import datetime
from uuid import UUID, uuid4

from trialscribe_events.contracts.job import JobRequested
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.outbox import OutboxRepository
from trialscribe_events.utils.constant import (
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
    MAX_JOB_PARAMETERS_BYTES,
)
from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.schemas.job import JobCreateRequest, JobListResponse, JobResponse
from trialscribe_worker.utils.constant import SERVICE_NAME
from trialscribe_worker.utils.enum import JobKind, JobStatus
from trialscribe_worker.utils.exceptions import (
    InvalidJobInputError,
    JobAlreadyFinishedError,
    JobNotFoundError,
    UnsupportedJobKindError,
)


class JobService:
    """Own the rules a job obeys before, during, and after the queue."""

    def __init__(
        self,
        jobs: JobRepository,
        progress: JobProgressStore,
        outbox: OutboxRepository,
        registry: EventRegistry,
        topic_prefix: str,
    ) -> None:
        self._jobs = jobs
        self._progress = progress
        self._outbox = outbox
        self._registry = registry
        self._topic_prefix = topic_prefix

    async def request_job(
        self,
        organization_id: UUID,
        account_id: UUID,
        request: JobCreateRequest,
        now: datetime,
    ) -> JobResponse:
        """Record a job and its queue message in one indivisible write.

        Sending the message to the broker from here would mean two things that can
        each succeed alone: publish first and a worker can be handed a job whose
        ticket has not committed, then give up and discard it; commit first and a
        crash leaves a ticket nobody was ever told about. A bounded retry only
        narrows that window — it was measured closing on a real broker (bug B29).
        Writing the message into the outbox beside the ticket removes the question
        entirely: the message exists exactly when the job does. A relay hands it to
        the broker afterwards.
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
        await self._enqueue(job, now)
        return self._response(job, None)

    async def get_job(self, organization_id: UUID, job_id: UUID) -> JobResponse:
        """Return one job, with the higher of its live and durable progress."""

        job = await self._jobs.get(organization_id, job_id)
        if job is None:
            raise JobNotFoundError
        return self._response(job, await self._progress.get_progress(job_id))

    async def list_jobs(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        kind: str | None,
        limit: int,
    ) -> JobListResponse:
        """Return the newest tickets for a conversation, with live progress."""

        jobs = await self._jobs.list_for_conversation(
            organization_id,
            conversation_id,
            kind,
            limit,
        )
        items: list[JobResponse] = []
        for job in jobs:
            items.append(self._response(job, await self._progress.get_progress(job.id)))
        return JobListResponse(items=items)

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

    async def _enqueue(self, job: Job, now: datetime) -> None:
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
        await self._outbox.enqueue(
            self._registry.topic_of(self._topic_prefix, envelope),
            envelope,
        )

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
