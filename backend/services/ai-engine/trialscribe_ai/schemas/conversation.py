"""Public conversation workspace contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trialscribe_ai.utils.constant import (
    COLLABORATOR_LIMIT,
    CONVERSATION_CONTENT_MAX_LENGTH,
    CONVERSATION_TITLE_MAX_LENGTH,
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MESSAGE_CONTENT_VALIDATION_MESSAGE,
    TITLE_VALIDATION_MESSAGE,
)
from trialscribe_ai.utils.enum import ConversationStatus, MessageRole


def _normalized_text(value: str, maximum: int, message: str) -> str:
    normalized = value.strip()
    if not 1 <= len(normalized) <= maximum:
        raise ValueError(message)
    return normalized


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _normalized_text(
            value,
            CONVERSATION_TITLE_MAX_LENGTH,
            TITLE_VALIDATION_MESSAGE,
        )


class ConversationRenameRequest(ConversationCreateRequest):
    """Rename an existing conversation with the same title rules."""


class ConversationCollaboratorsReplaceRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    account_ids: list[UUID] = Field(max_length=COLLABORATOR_LIMIT)

    @field_validator("account_ids")
    @classmethod
    def reject_duplicate_accounts(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Collaborator account IDs must be unique")
        return value


class ConversationMessageCreateRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _normalized_text(
            value,
            CONVERSATION_CONTENT_MAX_LENGTH,
            MESSAGE_CONTENT_VALIDATION_MESSAGE,
        )


class ConversationPageQuery(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    archived: bool = False


class MessagePageQuery(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)


class ConversationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    owner_account_id: UUID
    title: str
    status: ConversationStatus
    collaborator_account_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    archived_at: datetime | None


class ConversationMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    organization_id: UUID
    author_account_id: UUID | None
    role: MessageRole
    content: str
    sequence: int
    created_at: datetime


class ConversationPageResponse(BaseModel):
    items: list[ConversationResponse]
    next_cursor: str | None


class ConversationMessagePageResponse(BaseModel):
    items: list[ConversationMessageResponse]
    next_cursor: str | None
