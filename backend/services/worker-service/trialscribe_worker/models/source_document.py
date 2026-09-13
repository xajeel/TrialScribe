"""A conversation file the worker may read without owning the documents table."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """The bytes and status of one tenant-scoped upload."""

    id: UUID
    organization_id: UUID
    conversation_id: UUID
    kind: str
    content_type: str
    status: str
    error: str | None
    content: bytes


@dataclass(frozen=True, slots=True)
class SourceDocumentMetadata:
    """Upload facts needed to score readiness without loading file bytes."""

    id: UUID
    filename: str
    status: str
    updated_at: datetime
