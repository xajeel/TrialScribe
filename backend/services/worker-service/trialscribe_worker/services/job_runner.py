"""Run one job, and make sure it ends with exactly one recorded outcome."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime
from trialscribe_events.config import EventBusSettings
from trialscribe_events.contracts.job import JobRequested
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.logs import event_context, get_event_logger

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.job import Job
from trialscribe_worker.repositories.job_progress import JobProgressStore
from trialscribe_worker.repositories.jobs import JobRepository
from trialscribe_worker.utils.constant import (
    MAX_PROGRESS,
    MIN_PROGRESS,
)
from trialscribe_worker.utils.enum import JobErrorCode, JobKind, JobStatus
from trialscribe_worker.utils.exceptions import (
    JobAttemptFailedError,
    JobCancelledError,
    JobNotFoundError,
)

logger = get_event_logger(__name__)


@dataclass(slots=True)
class JobContext:
    """What a pipeline is given: its inputs, and two ways to talk back."""

    job_id: UUID
    attempt: int
    parameters: dict[str, Any]
    report: Callable[[int], Awaitable[None]]
    check_cancelled: Callable[[], Awaitable[None]]
    organization_id: UUID
    account_id: UUID
    conversation_id: UUID | None = None
    gateway: object | None = None
    evidence: object | None = None
    sources: object | None = None
    max_attempts: int = 1


class JobPipeline(Protocol):
    """One kind of background work."""

    async def __call__(self, context: JobContext) -> None: ...


@dataclass(slots=True)
class _RunState:
    """What this attempt has already told the database."""

    persisted: int = MIN_PROGRESS
    cancel_requested: bool = False
    reported: list[int] = field(default_factory=list)


class JobRunner:
    """Turn one `job.requested` record into one durable job outcome.

    The outcome is written into the same transaction that records the record as
    handled, so a job can never be marked done by a write that was rolled back.
    Progress and the running/retrying markers use their own short transactions,
    because a caller has to be able to see them while the job is still going.
    """

    def __init__(
        self,
        runtime: DatabaseRuntime,
        progress: JobProgressStore,
        settings: WorkerSettings,
        event_settings: EventBusSettings,
        pipelines: dict[JobKind, JobPipeline],
    ) -> None:
        self._runtime = runtime
        self._progress = progress
        self._settings = settings
        self._event_settings = event_settings
        self._pipelines = pipelines

    async def handle(
        self,
        envelope: EventEnvelope,
        payload: BaseModel,
        session: AsyncSession,
    ) -> None:
        """Handle one job request, in the transaction that also claims it."""

        request = JobRequested.model_validate(payload.model_dump())
        job = await self._claim(request.job_id, envelope)
        if job is None:
            return

        pipeline = self._pipeline_for(job.kind)
        if pipeline is None:
            logger.error(
                "job.unsupported_kind",
                extra={"event_context": event_context(envelope, reason=job.kind)},
            )
            await self._finish(
                session,
                job.id,
                JobStatus.FAILED,
                JobErrorCode.UNSUPPORTED_KIND,
            )
            return

        state = _RunState()
        context = JobContext(
            job_id=job.id,
            attempt=job.attempt,
            parameters=dict(job.parameters or {}),
            report=lambda percent: self._report(job.id, state, percent),
            check_cancelled=lambda: self._check_cancelled(job.id, state),
            organization_id=job.organization_id,
            account_id=job.requested_by_account_id,
            conversation_id=job.conversation_id,
            max_attempts=self._event_settings.max_delivery_attempts,
        )

        try:
            await pipeline(context)
        except JobCancelledError:
            logger.info(
                "job.cancelled",
                extra={"event_context": event_context(envelope, attempt=job.attempt)},
            )
            await self._finish(
                session,
                job.id,
                JobStatus.CANCELLED,
                JobErrorCode.CANCELLED,
            )
            return
        except Exception:
            await self._after_failure(session, job, envelope)
            return

        await self._finish(
            session,
            job.id,
            JobStatus.SUCCEEDED,
            None,
            progress=MAX_PROGRESS,
        )

    async def _claim(self, job_id: UUID, envelope: EventEnvelope) -> Job | None:
        """Take the job, or explain why there is nothing to take.

        A ticket that does not exist yet is not an error in the record — the
        request that created it may still be a millisecond from committing — so
        the failure travels out and the event backbone tries again.
        """

        async with self._runtime.transaction() as session:
            repository = JobRepository(session)
            job = await repository.claim(job_id, self._now())
            if job is not None:
                return job
            if not await repository.exists(job_id):
                logger.warning(
                    "job.ticket_not_found",
                    extra={"event_context": event_context(envelope)},
                )
                raise JobNotFoundError
        logger.info(
            "job.already_settled",
            extra={"event_context": event_context(envelope)},
        )
        return None

    async def _after_failure(
        self,
        session: AsyncSession,
        job: Job,
        envelope: EventEnvelope,
    ) -> None:
        """Retry while attempts remain; otherwise record the failure as the answer.

        The exception itself is never re-raised on the last attempt: a job that
        failed is a real outcome belonging on its ticket, not a broken record
        belonging in the dead-letter topic.
        """

        logger.warning(
            "job.attempt_failed",
            extra={"event_context": event_context(envelope, attempt=job.attempt)},
        )
        if job.attempt < self._event_settings.max_delivery_attempts:
            async with self._runtime.transaction() as retry_session:
                await JobRepository(retry_session).mark_retrying(job.id, self._now())
            raise JobAttemptFailedError
        await self._finish(
            session,
            job.id,
            JobStatus.FAILED,
            JobErrorCode.HANDLER_FAILED,
        )

    async def _finish(
        self,
        session: AsyncSession,
        job_id: UUID,
        status: JobStatus,
        error_code: JobErrorCode | None,
        progress: int | None = None,
    ) -> None:
        """Record the job's one outcome, then tidy up without risking it.

        The terminal row goes into the event consumer's transaction, so anything
        raised after it rolls that row back together with the receipt saying the
        event was handled — the job would then be rerun and finally dead-lettered
        while its ticket still read `running` (bug B28). Clearing the live
        progress keys is throwaway housekeeping and they already carry a TTL, so
        a failure here is logged and swallowed rather than allowed to undo an
        answer that is already true.

        The clear deliberately stays after the terminal write: a leftover key can
        only equal or lag the durable value, so reading it can never overstate
        how far a job got.
        """

        await JobRepository(session).finish(
            job_id,
            status,
            self._now(),
            error_code=error_code,
            progress=progress,
        )
        try:
            await self._progress.clear(job_id)
        except Exception:
            logger.warning(
                "job.progress_cleanup_failed",
                extra={"event_context": event_context(reason=status.value)},
            )

    async def _report(self, job_id: UUID, state: _RunState, percent: int) -> None:
        """Publish progress, and write it down often enough to survive a restart."""

        bounded = max(MIN_PROGRESS, min(MAX_PROGRESS, percent))
        state.reported.append(bounded)
        await self._progress.set_progress(job_id, bounded)
        if bounded - state.persisted < self._settings.progress_persist_step:
            return
        async with self._runtime.transaction() as session:
            cancel_requested_at = await JobRepository(session).record_progress(
                job_id,
                bounded,
            )
        state.persisted = bounded
        state.cancel_requested = state.cancel_requested or cancel_requested_at is not None

    async def _check_cancelled(self, job_id: UUID, state: _RunState) -> None:
        """Stop the job if anyone asked it to, believing either source."""

        if state.cancel_requested or await self._progress.is_cancelled(job_id):
            raise JobCancelledError

    def _pipeline_for(self, kind: str) -> JobPipeline | None:
        try:
            return self._pipelines.get(JobKind(kind))
        except ValueError:
            return None

    def _now(self) -> datetime:
        return datetime.now(UTC)
