"""The request that puts one piece of background work onto the queue."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.constant import (
    JOB_EVENT_DOMAIN,
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
    MAX_JOB_KIND_LENGTH,
)


class JobRequested(BaseModel):
    """Ask a worker to run one job that has already been recorded.

    ``kind`` stays plain text rather than an enumeration: a service that has not
    yet learned about a new kind must still be able to read the record, decide it
    cannot serve it, and say so, instead of failing to parse the message at all.
    """

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    job_id: UUID
    kind: str = Field(min_length=1, max_length=MAX_JOB_KIND_LENGTH)
    organization_id: UUID
    conversation_id: UUID | None = None
    requested_by_account_id: UUID
    attempt: int = Field(default=1, ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


def register_job_events(registry: EventRegistry) -> EventRegistry:
    """Teach a registry the job contracts, and hand it back for chaining."""

    registry.register(
        JOB_REQUESTED_EVENT_TYPE,
        JOB_EVENT_VERSION,
        JOB_EVENT_DOMAIN,
        JobRequested,
    )
    return registry
