"""What a caller sends to request background work, and what they get back."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from trialscribe_worker.utils.constant import MAX_JOB_KIND_LENGTH
from trialscribe_worker.utils.enum import JobErrorCode, JobStatus


class JobCreateRequest(BaseModel):
    """Ask for one piece of background work."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    kind: str = Field(min_length=1, max_length=MAX_JOB_KIND_LENGTH)
    conversation_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    """The ticket: everything a caller may know about one job."""

    model_config = ConfigDict(hide_input_in_errors=True)

    id: UUID
    organization_id: UUID
    conversation_id: UUID | None
    kind: str
    status: JobStatus
    progress: int
    attempt: int
    error_code: JobErrorCode | None
    correlation_id: UUID
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
