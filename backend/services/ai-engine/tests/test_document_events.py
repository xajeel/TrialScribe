import asyncio
from datetime import UTC, datetime
from uuid import UUID

from trialscribe_events.contracts.document import (
    DocumentDeleted,
    DocumentUploaded,
    register_document_events,
)
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.models.outbox_event import OutboxEvent
from trialscribe_events.registry import EventRegistry

from trialscribe_ai.models.document import Document
from trialscribe_ai.services.document_events import DocumentEventPublisher
from trialscribe_ai.utils.constant import SERVICE_NAME

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("51000000-0000-4000-8000-000000000001")
CONVERSATION_ID = UUID("51000000-0000-4000-8000-000000000002")
ACCOUNT_ID = UUID("51000000-0000-4000-8000-000000000003")
DOCUMENT_ID = UUID("51000000-0000-4000-8000-000000000004")
TOPIC_PREFIX = "trialscribe"
CONTENT_KEYS = frozenset({"content", "filename", "byte_size", "error", "status"})


class FakeOutbox:
    def __init__(self) -> None:
        self.stored: list[OutboxEvent] = []

    async def enqueue(self, topic: str, envelope: EventEnvelope) -> OutboxEvent:
        record = OutboxEvent(
            topic=topic,
            partition_key=envelope.partition_key(),
            payload=envelope.to_bytes(),
            headers={name: value.decode("utf-8") for name, value in envelope.headers()},
        )
        self.stored.append(record)
        return record


def publisher() -> tuple[DocumentEventPublisher, FakeOutbox]:
    outbox = FakeOutbox()
    return (
        DocumentEventPublisher(
            outbox,  # type: ignore[arg-type]
            register_document_events(EventRegistry()),
            TOPIC_PREFIX,
        ),
        outbox,
    )


def make_document() -> Document:
    return Document(
        id=DOCUMENT_ID,
        conversation_id=CONVERSATION_ID,
        organization_id=ORGANIZATION_ID,
        uploaded_by_account_id=ACCOUNT_ID,
        kind="research_document",
        filename="secret-notes.txt",
        content_type="text/plain",
        byte_size=12,
        status="pending",
        error=None,
        content=b"secret bytes",
        created_at=NOW,
        updated_at=NOW,
    )


def stored_envelope(outbox: FakeOutbox) -> EventEnvelope:
    assert len(outbox.stored) == 1
    record = outbox.stored[0]
    assert record.topic == "trialscribe.document.v1"
    assert record.partition_key == str(DOCUMENT_ID).encode("utf-8")
    return EventEnvelope.from_bytes(record.payload)


def test_upload_letter_names_the_document_and_omits_file_bytes() -> None:
    events, outbox = publisher()

    asyncio.run(events.record_uploaded(make_document(), NOW))

    envelope = stored_envelope(outbox)
    assert envelope.event_type == "document.uploaded"
    assert envelope.subject == str(DOCUMENT_ID)
    assert envelope.producer == SERVICE_NAME
    assert envelope.organization_id == ORGANIZATION_ID
    assert CONTENT_KEYS.isdisjoint(envelope.payload)
    payload = DocumentUploaded.model_validate(envelope.payload)
    assert payload.document_id == DOCUMENT_ID
    assert payload.conversation_id == CONVERSATION_ID
    assert payload.uploaded_by_account_id == ACCOUNT_ID
    assert payload.kind == "research_document"


def test_delete_letter_names_the_removed_document() -> None:
    events, outbox = publisher()

    asyncio.run(events.record_deleted(make_document(), NOW))

    envelope = stored_envelope(outbox)
    assert envelope.event_type == "document.deleted"
    assert envelope.subject == str(DOCUMENT_ID)
    assert CONTENT_KEYS.isdisjoint(envelope.payload)
    payload = DocumentDeleted.model_validate(envelope.payload)
    assert payload.document_id == DOCUMENT_ID
    assert payload.kind == "research_document"
