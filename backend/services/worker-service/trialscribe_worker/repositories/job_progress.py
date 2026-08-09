"""The fast, throwaway half of a job's state: live progress and "please stop".

Only `get`, `set`, and `delete` are used, so a test double is an honest model of
the real client rather than an invention that agrees with whatever the code hopes
for (bug B23).
"""

from typing import Any, Protocol
from uuid import UUID

from trialscribe_worker.utils.constant import (
    JOB_CANCEL_FLAG_VALUE,
    JOB_CANCEL_KEY_PREFIX,
    JOB_PROGRESS_KEY_PREFIX,
    MAX_PROGRESS,
    MIN_PROGRESS,
)


class KeyValueStore(Protocol):
    """The three Redis commands this store is allowed to depend on."""

    async def get(self, name: str) -> Any: ...

    async def set(self, name: str, value: str, ex: int | None = None) -> Any: ...

    async def delete(self, *names: str) -> Any: ...


class JobProgressStore:
    """Keep the live progress and cancellation flag for running jobs."""

    def __init__(self, client: KeyValueStore, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    def progress_key(self, job_id: UUID) -> str:
        return f"{JOB_PROGRESS_KEY_PREFIX}{job_id}"

    def cancel_key(self, job_id: UUID) -> str:
        return f"{JOB_CANCEL_KEY_PREFIX}{job_id}"

    async def set_progress(self, job_id: UUID, progress: int) -> None:
        """Publish how far along a job is, for as long as anyone cares."""

        await self._client.set(
            self.progress_key(job_id),
            str(progress),
            ex=self._ttl_seconds,
        )

    async def get_progress(self, job_id: UUID) -> int | None:
        """Return the live progress, or nothing at all if it is not usable.

        A missing, unreadable, or out-of-range value reads as "unknown" so the
        caller falls back to the durable watermark instead of showing nonsense.
        """

        raw_value = await self._client.get(self.progress_key(job_id))
        if raw_value is None:
            return None
        if isinstance(raw_value, bytes | bytearray):
            raw_value = raw_value.decode("utf-8", errors="replace")
        try:
            progress = int(str(raw_value).strip())
        except ValueError:
            return None
        if progress < MIN_PROGRESS or progress > MAX_PROGRESS:
            return None
        return progress

    async def request_cancel(self, job_id: UUID) -> None:
        """Raise the flag a running job checks between its steps."""

        await self._client.set(
            self.cancel_key(job_id),
            JOB_CANCEL_FLAG_VALUE,
            ex=self._ttl_seconds,
        )

    async def is_cancelled(self, job_id: UUID) -> bool:
        """Report whether someone asked this job to stop."""

        return await self._client.get(self.cancel_key(job_id)) is not None

    async def clear(self, job_id: UUID) -> None:
        """Forget a finished job's live state; the ticket keeps the outcome."""

        await self._client.delete(self.progress_key(job_id), self.cancel_key(job_id))
