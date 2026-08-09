import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.utils.constant import (
    CONTENT_TYPE_HEADER,
    EVENT_ID_HEADER,
    EVENT_TYPE_HEADER,
    EVENT_VERSION_HEADER,
)
from trialscribe_events.utils.exceptions import InvalidEventError

EVENT_ID = UUID("00000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000003")
CAUSATION_ID = UUID("00000000-0000-4000-8000-000000000004")
OCCURRED_AT = datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC)


def envelope_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "event_id": EVENT_ID,
        "event_type": "job.generation.requested",
        "event_version": 1,
        "occurred_at": OCCURRED_AT,
        "organization_id": ORGANIZATION_ID,
        "subject": str(EVENT_ID),
        "correlation_id": CORRELATION_ID,
        "causation_id": CAUSATION_ID,
        "producer": "ai-engine",
        "payload": {"section_code": "6.1"},
    }
    values.update(overrides)
    return values


def test_envelope_round_trips_through_kafka_bytes() -> None:
    envelope = EventEnvelope(**envelope_values())

    restored = EventEnvelope.from_bytes(envelope.to_bytes())

    assert restored == envelope
    assert restored.payload == {"section_code": "6.1"}
    assert restored.causation_id == CAUSATION_ID


def test_unknown_fields_are_ignored_so_producers_can_add_them() -> None:
    values = envelope_values()
    values["deployment_region"] = "eu-west-1"

    envelope = EventEnvelope(**values)

    assert not hasattr(envelope, "deployment_region")
    assert envelope.event_id == EVENT_ID


def test_naive_occurred_at_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        EventEnvelope(**envelope_values(occurred_at=datetime(2026, 8, 8, 12, 30, 0)))

    assert "occurred_at must be timezone-aware" in str(error.value)


def test_aware_occurred_at_is_normalized_to_utc() -> None:
    local = datetime(2026, 8, 8, 17, 30, 0, tzinfo=timezone(timedelta(hours=5)))

    envelope = EventEnvelope(**envelope_values(occurred_at=local))

    assert envelope.occurred_at == OCCURRED_AT
    assert envelope.occurred_at.tzinfo == UTC


@pytest.mark.parametrize(
    "event_type",
    ["Job.Generation.Requested", "job", "job..requested", "job.generation-requested", ""],
)
def test_event_type_must_be_dot_separated_lower_snake_case(event_type: str) -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(**envelope_values(event_type=event_type))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_version", 0),
        ("subject", ""),
        ("subject", "s" * 201),
        ("producer", ""),
        ("producer", "p" * 101),
    ],
)
def test_rejects_values_outside_the_documented_bounds(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(**envelope_values(**{field: value}))


def test_envelope_is_immutable() -> None:
    envelope = EventEnvelope(**envelope_values())

    with pytest.raises(ValidationError):
        envelope.subject = "another-subject"  # type: ignore[misc]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not-json-do-not-print",
        b"{}",
        b'{"event_type": "job.generation.requested", "payload": {"secret": "do-not-print"}}',
        b"\xff\xfe\x00do-not-print",
    ],
)
def test_unreadable_bytes_raise_without_echoing_the_record(data: bytes) -> None:
    with pytest.raises(InvalidEventError) as error:
        EventEnvelope.from_bytes(data)

    assert str(error.value) == "event envelope is not valid"
    assert "do-not-print" not in str(error.value)


def test_partition_key_is_the_subject() -> None:
    envelope = EventEnvelope(**envelope_values(subject="conversation-42"))

    assert envelope.partition_key() == b"conversation-42"


def test_headers_carry_routing_facts_only() -> None:
    envelope = EventEnvelope(**envelope_values())

    headers = dict(envelope.headers())

    assert headers == {
        EVENT_ID_HEADER: str(EVENT_ID).encode(),
        EVENT_TYPE_HEADER: b"job.generation.requested",
        EVENT_VERSION_HEADER: b"1",
        CONTENT_TYPE_HEADER: b"application/json",
    }
    assert b"6.1" not in b"".join(headers.values())


def test_serialized_form_keeps_every_contract_field() -> None:
    envelope = EventEnvelope(**envelope_values())

    document = json.loads(envelope.to_bytes())

    assert set(document) == {
        "event_id",
        "event_type",
        "event_version",
        "occurred_at",
        "organization_id",
        "subject",
        "correlation_id",
        "causation_id",
        "producer",
        "payload",
    }
