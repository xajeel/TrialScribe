"""Public contracts for ICH M11 section workspaces."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trialscribe_ai.utils.constant import (
    DEFAULT_PAGE_LIMIT,
    M11_CONTENT_MAX_LENGTH,
    M11_CONTENT_VALIDATION_MESSAGE,
    M11_INSTRUCTIONS_MAX_LENGTH,
    M11_INSTRUCTIONS_VALIDATION_MESSAGE,
    MAX_PAGE_LIMIT,
)
from trialscribe_ai.utils.enum import M11RevisionAction, M11SectionStatus


def _normalized_optional_text(value: str | None, maximum: int, message: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(message)
    return normalized


class M11CatalogSectionResponse(BaseModel):
    number: str
    title: str
    position: int


class M11CatalogResponse(BaseModel):
    version: str
    items: list[M11CatalogSectionResponse]


class M11SectionReviseRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    expected_revision: int = Field(ge=0)
    instructions: str | None = None
    content: str | None = None

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str | None) -> str | None:
        return _normalized_optional_text(
            value,
            M11_INSTRUCTIONS_MAX_LENGTH,
            M11_INSTRUCTIONS_VALIDATION_MESSAGE,
        )

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        return _normalized_optional_text(
            value,
            M11_CONTENT_MAX_LENGTH,
            M11_CONTENT_VALIDATION_MESSAGE,
        )

    @model_validator(mode="after")
    def require_change(self) -> "M11SectionReviseRequest":
        if self.instructions is None and self.content is None:
            raise ValueError("At least one section field must be supplied")
        return self


class M11SectionTransitionRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    expected_revision: int = Field(ge=0)


class M11RevisionPageQuery(BaseModel):
    after_revision: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)


class M11SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    organization_id: UUID
    catalog_version: str
    section_number: str
    title: str
    position: int
    instructions: str
    content: str
    status: M11SectionStatus
    current_revision: int
    completed_at: datetime | None
    completed_by_account_id: UUID | None
    created_at: datetime
    updated_at: datetime


class M11SectionRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    section_id: UUID
    conversation_id: UUID
    organization_id: UUID
    revision_number: int
    action: M11RevisionAction
    instructions: str
    content: str
    status: M11SectionStatus
    author_account_id: UUID | None
    created_at: datetime


class M11SectionWorkspaceResponse(BaseModel):
    catalog_version: str
    items: list[M11SectionResponse]


class M11SectionRevisionPageResponse(BaseModel):
    items: list[M11SectionRevisionResponse]
    next_after_revision: int | None
