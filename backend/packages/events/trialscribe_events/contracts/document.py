"""The letters that say a conversation file was attached or removed."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.constant import (
    DOCUMENT_DELETED_EVENT_TYPE,
    DOCUMENT_EVENT_DOMAIN,
    DOCUMENT_EVENT_VERSION,
    DOCUMENT_UPLOADED_EVENT_TYPE,
    MAX_DOCUMENT_KIND_LENGTH,
)


class DocumentUploaded(BaseModel):
    """A conversation file is durable and ready for the worker to index.

    ``kind`` stays plain text rather than an enumeration so an older worker can
    still read the letter, decide it cannot index that kind, and say so.
    """

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    document_id: UUID
    conversation_id: UUID
    organization_id: UUID
    uploaded_by_account_id: UUID
    kind: str = Field(min_length=1, max_length=MAX_DOCUMENT_KIND_LENGTH)


class DocumentDeleted(BaseModel):
    """A conversation file was removed and its passages must go with it."""

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    document_id: UUID
    conversation_id: UUID
    organization_id: UUID
    kind: str = Field(min_length=1, max_length=MAX_DOCUMENT_KIND_LENGTH)


def register_document_events(registry: EventRegistry) -> EventRegistry:
    """Teach a registry the document contracts, and hand it back for chaining."""

    registry.register(
        DOCUMENT_UPLOADED_EVENT_TYPE,
        DOCUMENT_EVENT_VERSION,
        DOCUMENT_EVENT_DOMAIN,
        DocumentUploaded,
    )
    registry.register(
        DOCUMENT_DELETED_EVENT_TYPE,
        DOCUMENT_EVENT_VERSION,
        DOCUMENT_EVENT_DOMAIN,
        DocumentDeleted,
    )
    return registry
