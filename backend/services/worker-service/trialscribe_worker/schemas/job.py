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


class JobListResponse(BaseModel):
    """Newest matching tickets for one conversation."""

    items: list[JobResponse]


class GenerationAttemptPublic(BaseModel):
    """The latest per-section outcome a caller may see for one job.

    `prompt` and `content` are never selected or returned (B4).
    """

    section_number: str
    status: str
    error_code: str | None
    citation_ids: list[UUID]
    attempt: int


class GenerationAttemptListResponse(BaseModel):
    items: list[GenerationAttemptPublic]


class RewriteOptionPublic(BaseModel):
    """One proposed wording. Prompts are never included."""

    id: str
    text: str


class RewriteOptionListResponse(BaseModel):
    items: list[RewriteOptionPublic]


class ReadinessIssuePublic(BaseModel):
    """One finding. Chapter text is only included on section rows."""

    model_config = ConfigDict(hide_input_in_errors=True)

    id: str
    title: str
    detail: str
    severity: str
    code: str
    action: str
    action_label: str
    section_number: str | None = None


class ReadinessCitationPublic(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    resolved: int
    needing_review: int


class ReadinessSummaryPublic(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    total_sections: int
    done_sections: int
    draft_sections: int
    ready_sources: int
    pending_sources: int
    failed_sources: int
    latest_activity: str | None
    citations: ReadinessCitationPublic | None = None


class ReadinessSectionPublic(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    id: str
    section_number: str
    title: str
    position: int
    status: str
    revision: int
    words: int
    updated_at: str
    content: str
    issues: list[ReadinessIssuePublic]
    citations: ReadinessCitationPublic | None = None


class ReadinessResponse(BaseModel):
    """The newest stored check, or an unchecked empty result."""

    model_config = ConfigDict(hide_input_in_errors=True)

    checked: bool
    ready: bool
    stale: bool
    job_id: UUID | None
    computed_at: datetime | None
    protocol_title: str
    protocol_id: UUID
    summary: ReadinessSummaryPublic
    issues: list[ReadinessIssuePublic]
    sections: list[ReadinessSectionPublic]
