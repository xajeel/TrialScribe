from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry, dead_letter_topic, topic_for
from trialscribe_events.utils.exceptions import (
    EventContractError,
    EventRegistrationError,
    UnknownEventTypeError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000003")
OCCURRED_AT = datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC)


class JobRequested(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_id: str
    section_code: str


class OtherPayload(BaseModel):
    reference: str


def registry_with_job_requested() -> EventRegistry:
    registry = EventRegistry()
    registry.register("job.generation.requested", 1, "job", JobRequested)
    return registry


def test_topic_names_carry_prefix_domain_and_major_version() -> None:
    assert topic_for("trialscribe", "job", 1) == "trialscribe.job.v1"
    assert dead_letter_topic("trialscribe.job.v1") == "trialscribe.job.v1.dlq"


def test_registering_the_same_type_and_version_twice_is_rejected() -> None:
    registry = registry_with_job_requested()

    with pytest.raises(EventRegistrationError):
        registry.register("job.generation.requested", 1, "job", JobRequested)

    registry.register("job.generation.requested", 2, "job", OtherPayload)
    assert registry.resolve("job.generation.requested", 2).payload_model is OtherPayload


def test_unknown_type_and_unknown_version_are_rejected() -> None:
    registry = registry_with_job_requested()

    with pytest.raises(UnknownEventTypeError):
        registry.resolve("job.generation.cancelled", 1)
    with pytest.raises(UnknownEventTypeError):
        registry.resolve("job.generation.requested", 2)


def test_topics_are_sorted_and_deduplicated() -> None:
    registry = registry_with_job_requested()
    registry.register("job.generation.succeeded", 1, "job", OtherPayload)
    registry.register("document.ingestion.requested", 1, "document", OtherPayload)

    assert registry.topics("trialscribe") == (
        "trialscribe.document.v1",
        "trialscribe.job.v1",
    )


def test_build_then_decode_round_trips_the_payload() -> None:
    registry = registry_with_job_requested()

    envelope = registry.build(
        event_type="job.generation.requested",
        version=1,
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload=JobRequested(job_id="job-1", section_code="6.1"),
        occurred_at=OCCURRED_AT,
    )
    decoded = registry.decode(envelope)

    assert envelope.event_type == "job.generation.requested"
    assert envelope.event_version == 1
    assert envelope.organization_id == ORGANIZATION_ID
    assert envelope.occurred_at == OCCURRED_AT
    assert registry.topic_of("trialscribe", envelope) == "trialscribe.job.v1"
    assert isinstance(decoded, JobRequested)
    assert decoded.job_id == "job-1"
    assert decoded.section_code == "6.1"


def test_build_rejects_a_payload_of_the_wrong_registered_model() -> None:
    registry = registry_with_job_requested()

    with pytest.raises(EventContractError):
        registry.build(
            event_type="job.generation.requested",
            version=1,
            organization_id=ORGANIZATION_ID,
            subject="job-1",
            correlation_id=CORRELATION_ID,
            producer="ai-engine",
            payload=OtherPayload(reference="job-1"),
        )


def test_build_defaults_occurred_at_to_an_aware_utc_instant() -> None:
    registry = registry_with_job_requested()

    envelope = registry.build(
        event_type="job.generation.requested",
        version=1,
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload=JobRequested(job_id="job-1", section_code="6.1"),
    )

    assert envelope.occurred_at.tzinfo == UTC


def test_decode_rejects_a_payload_missing_a_required_field() -> None:
    registry = registry_with_job_requested()
    envelope = EventEnvelope(
        event_type="job.generation.requested",
        event_version=1,
        occurred_at=OCCURRED_AT,
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload={"job_id": "job-1"},
    )

    with pytest.raises(EventContractError) as error:
        registry.decode(envelope)

    assert str(error.value) == "event payload does not match its contract"


def test_decode_tolerates_a_payload_field_the_consumer_does_not_know() -> None:
    registry = registry_with_job_requested()
    envelope = EventEnvelope(
        event_type="job.generation.requested",
        event_version=1,
        occurred_at=OCCURRED_AT,
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload={"job_id": "job-1", "section_code": "6.1", "priority": "high"},
    )

    decoded = registry.decode(envelope)

    assert isinstance(decoded, JobRequested)
    assert decoded.job_id == "job-1"


def test_topic_of_rejects_an_envelope_this_registry_does_not_know() -> None:
    registry = registry_with_job_requested()
    envelope = EventEnvelope(
        event_type="job.generation.cancelled",
        event_version=1,
        occurred_at=OCCURRED_AT,
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload={},
    )

    with pytest.raises(UnknownEventTypeError):
        registry.topic_of("trialscribe", envelope)
