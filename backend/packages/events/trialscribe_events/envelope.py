"""The versioned envelope every TrialScribe service publishes and consumes."""

import re
from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from trialscribe_events.utils.constant import (
    CONTENT_TYPE,
    CONTENT_TYPE_HEADER,
    EVENT_ID_HEADER,
    EVENT_TYPE_HEADER,
    EVENT_TYPE_PATTERN,
    EVENT_VERSION_HEADER,
    INVALID_ENVELOPE_MESSAGE,
    MAX_EVENT_TYPE_LENGTH,
    MAX_PRODUCER_LENGTH,
    MAX_SUBJECT_LENGTH,
)
from trialscribe_events.utils.exceptions import InvalidEventError


class EventEnvelope(BaseModel):
    """Carry event identity, tenant context, versioning, and causation.

    Unknown fields are ignored so a newer producer can add one without breaking
    an older consumer. Removing or retyping a field is a breaking change and
    requires a new ``event_version`` and topic.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(min_length=1, max_length=MAX_EVENT_TYPE_LENGTH)
    event_version: int = Field(ge=1)
    occurred_at: datetime
    organization_id: UUID
    subject: str = Field(min_length=1, max_length=MAX_SUBJECT_LENGTH)
    correlation_id: UUID
    causation_id: UUID | None = None
    producer: str = Field(min_length=1, max_length=MAX_PRODUCER_LENGTH)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if re.fullmatch(EVENT_TYPE_PATTERN, value) is None:
            raise ValueError("event_type must be dot-separated lower snake case")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_utc_instant(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)

    def to_bytes(self) -> bytes:
        """Serialize the envelope to the JSON bytes carried by Kafka."""

        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Read an envelope from Kafka bytes without echoing the record back."""

        try:
            return cls.model_validate_json(data)
        except (ValidationError, ValueError, UnicodeDecodeError):
            raise InvalidEventError(INVALID_ENVELOPE_MESSAGE) from None

    def partition_key(self) -> bytes:
        """Return the key that keeps every event about one subject in order."""

        return self.subject.encode("utf-8")

    def headers(self) -> list[tuple[str, bytes]]:
        """Return routing headers that never carry payload content."""

        return [
            (EVENT_ID_HEADER, str(self.event_id).encode("utf-8")),
            (EVENT_TYPE_HEADER, self.event_type.encode("utf-8")),
            (EVENT_VERSION_HEADER, str(self.event_version).encode("utf-8")),
            (CONTENT_TYPE_HEADER, CONTENT_TYPE.encode("utf-8")),
        ]
