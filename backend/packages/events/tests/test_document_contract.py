import json
from uuid import UUID

import pytest

from trialscribe_events.contracts.document import (
    DocumentDeleted,
    DocumentUploaded,
    register_document_events,
)
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.constant import (
    DOCUMENT_DELETED_EVENT_TYPE,
    DOCUMENT_EVENT_DOMAIN,
    DOCUMENT_EVENT_VERSION,
    DOCUMENT_UPLOADED_EVENT_TYPE,
)
from trialscribe_events.utils.exceptions import EventRegistrationError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000111")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000112")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000113")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000114")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000115")
TOPIC_PREFIX = "trialscribe"


def registry() -> EventRegistry:
    return register_document_events(EventRegistry())


def uploaded() -> DocumentUploaded:
    return DocumentUploaded(
        document_id=DOCUMENT_ID,
        conversation_id=CONVERSATION_ID,
        organization_id=ORGANIZATION_ID,
        uploaded_by_account_id=ACCOUNT_ID,
        kind="research_document",
    )


def deleted() -> DocumentDeleted:
    return DocumentDeleted(
        document_id=DOCUMENT_ID,
        conversation_id=CONVERSATION_ID,
        organization_id=ORGANIZATION_ID,
        kind="research_document",
    )


def envelope(payload: DocumentUploaded | DocumentDeleted) -> EventEnvelope:
    event_type = (
        DOCUMENT_UPLOADED_EVENT_TYPE
        if isinstance(payload, DocumentUploaded)
        else DOCUMENT_DELETED_EVENT_TYPE
    )
    return registry().build(
        event_type=event_type,
        version=DOCUMENT_EVENT_VERSION,
        organization_id=ORGANIZATION_ID,
        subject=str(DOCUMENT_ID),
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload=payload,
    )


def test_document_letters_travel_on_their_own_versioned_topic() -> None:
    catalogue = registry()

    assert catalogue.topics(TOPIC_PREFIX) == ("trialscribe.document.v1",)
    assert catalogue.resolve(DOCUMENT_UPLOADED_EVENT_TYPE, DOCUMENT_EVENT_VERSION).domain == (
        DOCUMENT_EVENT_DOMAIN
    )
    assert catalogue.resolve(DOCUMENT_DELETED_EVENT_TYPE, DOCUMENT_EVENT_VERSION).domain == (
        DOCUMENT_EVENT_DOMAIN
    )


def test_an_upload_letter_survives_the_round_trip_through_kafka_bytes() -> None:
    original = envelope(uploaded())

    restored = EventEnvelope.from_bytes(original.to_bytes())
    decoded = registry().decode(restored)

    assert isinstance(decoded, DocumentUploaded)
    assert decoded == uploaded()
    assert restored.partition_key() == str(DOCUMENT_ID).encode("utf-8")


def test_a_delete_letter_survives_the_round_trip_through_kafka_bytes() -> None:
    original = envelope(deleted())

    restored = EventEnvelope.from_bytes(original.to_bytes())
    decoded = registry().decode(restored)

    assert isinstance(decoded, DocumentDeleted)
    assert decoded == deleted()
    assert restored.partition_key() == str(DOCUMENT_ID).encode("utf-8")


def test_a_field_added_by_a_newer_producer_is_ignored_rather_than_rejected() -> None:
    body = json.loads(envelope(uploaded()).to_bytes())
    body["payload"]["filename"] = "secret.pdf"
    body["payload"]["content"] = "should-not-matter"

    decoded = registry().decode(
        EventEnvelope.from_bytes(json.dumps(body).encode("utf-8"))
    )

    assert isinstance(decoded, DocumentUploaded)
    assert decoded.document_id == DOCUMENT_ID
    assert not hasattr(decoded, "filename")


def test_registering_the_document_contracts_twice_is_refused() -> None:
    catalogue = registry()

    with pytest.raises(EventRegistrationError):
        register_document_events(catalogue)
