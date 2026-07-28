"""AI-engine enum values shared across domain boundaries."""

from enum import StrEnum


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class DocumentKind(StrEnum):
    TRIAL_DATA = "trial_data"
    RESEARCH_DOCUMENT = "research_document"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class M11SectionStatus(StrEnum):
    DRAFT = "draft"
    DONE = "done"


class M11RevisionAction(StrEnum):
    REVISED = "revised"
    DONE = "done"
    REOPENED = "reopened"
