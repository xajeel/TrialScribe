"""Durable job state, changed only by updates that name the status they expect.

Every statement here reads its outcome from the row it returns. Row counts are
never consulted: an ORM-entity write reports -1 rather than the number of rows it
touched, which once made a duplicate guard answer "already handled" every single
time (bug B23).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.models.job import Job
from trialscribe_worker.utils.enum import (
    CLAIMABLE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    JobErrorCode,
    JobStatus,
)

CLAIMABLE_VALUES = tuple(sorted(status.value for status in CLAIMABLE_JOB_STATUSES))
TERMINAL_VALUES = tuple(sorted(status.value for status in TERMINAL_JOB_STATUSES))


class JobRepository:
    """Read and advance job tickets without ever losing an outcome."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: Job) -> Job:
        """Record a newly requested job so the queue has something to point at."""

        self._session.add(job)
        await self._session.flush()
        return job

    async def get(self, organization_id: UUID, job_id: UUID) -> Job | None:
        """Return one job, and only to the organization that owns it."""

        statement = select(Job).where(
            Job.id == job_id,
            Job.organization_id == organization_id,
        )
        return (await self._session.execute(statement)).scalars().first()

    async def exists(self, job_id: UUID) -> bool:
        """Report whether a job row has landed yet, ignoring tenancy."""

        statement = select(Job.id).where(Job.id == job_id)
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def claim(self, job_id: UUID, now: datetime) -> Job | None:
        """Take ownership of a job that has not finished, counting the attempt.

        Returns nothing when the job already reached a terminal status, which is
        how a cancelled or completed job survives a redelivered record.
        """

        statement = (
            update(Job)
            .where(Job.id == job_id, Job.status.in_(CLAIMABLE_VALUES))
            .values(
                status=JobStatus.RUNNING.value,
                attempt=Job.attempt + 1,
                started_at=func.coalesce(Job.started_at, now),
                updated_at=now,
            )
            .returning(Job)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def mark_retrying(self, job_id: UUID, now: datetime) -> bool:
        """Park a running job between attempts."""

        statement = (
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
            .values(status=JobStatus.RETRYING.value, updated_at=now)
            .returning(Job.id)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def finish(
        self,
        job_id: UUID,
        status: JobStatus,
        now: datetime,
        *,
        error_code: JobErrorCode | None = None,
        progress: int | None = None,
    ) -> bool:
        """Write the one outcome a running job is allowed to end with."""

        values: dict[str, object] = {
            "status": status.value,
            "error_code": None if error_code is None else error_code.value,
            "finished_at": now,
            "updated_at": now,
        }
        if progress is not None:
            values["progress"] = func.greatest(Job.progress, progress)
        statement = (
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
            .values(**values)
            .returning(Job.id)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def record_progress(self, job_id: UUID, progress: int) -> datetime | None:
        """Raise the durable progress watermark and read back any stop request.

        `GREATEST` means a retried attempt counting up from zero can never pull
        the number down, and the row comes back either way so a cancellation that
        arrived while Redis was unavailable is still noticed.
        """

        statement = (
            update(Job)
            .where(Job.id == job_id)
            .values(progress=func.greatest(Job.progress, progress))
            .returning(Job.cancel_requested_at)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def cancel_queued(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> Job | None:
        """Stop a job outright while it is still waiting to be picked up."""

        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.organization_id == organization_id,
                Job.status == JobStatus.QUEUED.value,
            )
            .values(
                status=JobStatus.CANCELLED.value,
                error_code=JobErrorCode.CANCELLED.value,
                cancel_requested_at=now,
                finished_at=now,
                updated_at=now,
            )
            .returning(Job)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def request_cancel(
        self,
        organization_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> Job | None:
        """Ask a job that has already started to stop at its next checkpoint."""

        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.organization_id == organization_id,
                Job.status.notin_(TERMINAL_VALUES),
            )
            .values(
                cancel_requested_at=func.coalesce(Job.cancel_requested_at, now),
                updated_at=now,
            )
            .returning(Job)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(statement)).scalars().first()
