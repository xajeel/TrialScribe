"""Public conversation document contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from trialscribe_ai.utils.constant import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from trialscribe_ai.utils.enum import DocumentKind, DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    organization_id: UUID
    uploaded_by_account_id: UUID | None
    kind: DocumentKind
    filename: str
    content_type: str
    byte_size: int
    status: DocumentStatus
    error: str | None
    created_at: datetime
    updated_at: datetime


class DocumentPageQuery(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)


class DocumentPageResponse(BaseModel):
    items: list[DocumentResponse]
    next_cursor: str | None
