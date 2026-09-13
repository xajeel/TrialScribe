"""What one service writes, another service must be able to read.

The golden file is the agreement. `ProducerProbe` stands in for a service that was
updated recently; `ConsumerProbe` stands in for one that has not been updated yet.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.exceptions import EventContractError, UnknownEventTypeError

GOLDEN = Path(__file__).parent / "golden" / "contract_probe_recorded_v1.json"
EVENT_TYPE = "contract.probe.recorded"
EVENT_ID = UUID("11111111-1111-4111-8111-111111111111")
ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
CORRELATION_ID = UUID("33333333-3333-4333-8333-333333333333")
CAUSATION_ID = UUID("44444444-4444-4444-8444-444444444444")
OCCURRED_AT = datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC)


class ConsumerProbe(BaseModel):
    """The payload the older, not-yet-updated service knows about."""

    model_config = ConfigDict(extra="ignore")

    probe_id: str
    recorded_value: str


class ProducerProbe(BaseModel):
    """The same payload after a newer service added one field."""

    model_config = ConfigDict(extra="ignore")

    probe_id: str
    recorded_value: str
    recorded_region: str = "eu-west-1"


class ProbeV2(BaseModel):
    probe_id: str


def consumer_registry() -> EventRegistry:
    registry = EventRegistry()
    registry.register(EVENT_TYPE, 1, "contract", ConsumerProbe)
    return registry


def producer_registry() -> EventRegistry:
    registry = EventRegistry()
    registry.register(EVENT_TYPE, 1, "contract", ProducerProbe)
    return registry


def golden_bytes() -> bytes:
    return GOLDEN.read_bytes()


def test_golden_bytes_carry_every_field_the_contract_requires() -> None:
    envelope = EventEnvelope.from_bytes(golden_bytes())

    assert envelope.event_id == EVENT_ID
    assert envelope.event_type == EVENT_TYPE
    assert envelope.event_version == 1
    assert envelope.occurred_at == OCCURRED_AT
    assert envelope.organization_id == ORGANIZATION_ID
    assert envelope.subject == "probe-1"
    assert envelope.correlation_id == CORRELATION_ID
    assert envelope.causation_id == CAUSATION_ID
    assert envelope.producer == "ai-engine"


def test_the_receiving_service_can_read_the_golden_payload() -> None:
    envelope = EventEnvelope.from_bytes(golden_bytes())

    payload = consumer_registry().decode(envelope)

    assert isinstance(payload, ConsumerProbe)
    assert payload.probe_id == "probe-1"
    assert payload.recorded_value == "7"


def test_a_newer_producer_field_does_not_break_an_older_consumer() -> None:
    sent = producer_registry().build(
        event_type=EVENT_TYPE,
        version=1,
        organization_id=ORGANIZATION_ID,
        subject="probe-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload=ProducerProbe(probe_id="probe-1", recorded_value="7"),
        occurred_at=OCCURRED_AT,
    )

    received = EventEnvelope.from_bytes(sent.to_bytes())
    payload = consumer_registry().decode(received)

    assert "recorded_region" in received.payload
    assert isinstance(payload, ConsumerProbe)
    assert payload.recorded_value == "7"


def test_a_newer_envelope_field_does_not_break_an_older_consumer() -> None:
    document = json.loads(golden_bytes())
    document["deployment_region"] = "eu-west-1"

    envelope = EventEnvelope.from_bytes(json.dumps(document).encode("utf-8"))

    assert envelope.event_id == EVENT_ID
    assert isinstance(consumer_registry().decode(envelope), ConsumerProbe)


def test_a_payload_missing_a_required_field_is_refused() -> None:
    document = json.loads(golden_bytes())
    del document["payload"]["recorded_value"]
    envelope = EventEnvelope.from_bytes(json.dumps(document).encode("utf-8"))

    with pytest.raises(EventContractError):
        consumer_registry().decode(envelope)


def test_a_version_the_consumer_does_not_know_is_refused() -> None:
    document = json.loads(golden_bytes())
    document["event_version"] = 2
    envelope = EventEnvelope.from_bytes(json.dumps(document).encode("utf-8"))

    with pytest.raises(UnknownEventTypeError):
        consumer_registry().decode(envelope)


def test_adding_a_second_version_leaves_the_first_readable() -> None:
    registry = consumer_registry()
    registry.register(EVENT_TYPE, 2, "contract", ProbeV2)

    envelope = EventEnvelope.from_bytes(golden_bytes())

    assert isinstance(registry.decode(envelope), ConsumerProbe)
    assert registry.topics("trialscribe") == (
        "trialscribe.contract.v1",
        "trialscribe.contract.v2",
    )


def test_reading_and_rewriting_the_golden_message_changes_nothing() -> None:
    envelope = EventEnvelope.from_bytes(golden_bytes())

    assert json.loads(envelope.to_bytes()) == json.loads(golden_bytes())


def test_the_golden_message_is_addressed_to_the_expected_topic() -> None:
    envelope = EventEnvelope.from_bytes(golden_bytes())

    assert consumer_registry().topic_of("trialscribe", envelope) == "trialscribe.contract.v1"
