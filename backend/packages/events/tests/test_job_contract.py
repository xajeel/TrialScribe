import json
from uuid import UUID

import pytest

from trialscribe_events.contracts.job import JobRequested, register_job_events
from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.registry import EventRegistry
from trialscribe_events.utils.constant import (
    JOB_EVENT_VERSION,
    JOB_REQUESTED_EVENT_TYPE,
)
from trialscribe_events.utils.exceptions import (
    EventContractError,
    EventRegistrationError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000011")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000012")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000013")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000014")
JOB_ID = UUID("00000000-0000-4000-8000-000000000015")
TOPIC_PREFIX = "trialscribe"


def registry() -> EventRegistry:
    return register_job_events(EventRegistry())


def payload() -> JobRequested:
    return JobRequested(
        job_id=JOB_ID,
        kind="probe",
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        requested_by_account_id=ACCOUNT_ID,
        attempt=1,
        parameters={"steps": 4},
    )


def envelope() -> EventEnvelope:
    return registry().build(
        event_type=JOB_REQUESTED_EVENT_TYPE,
        version=JOB_EVENT_VERSION,
        organization_id=ORGANIZATION_ID,
        subject=str(JOB_ID),
        correlation_id=CORRELATION_ID,
        producer="worker-service",
        payload=payload(),
    )


def test_job_requests_travel_on_their_own_versioned_topic() -> None:
    catalogue = registry()

    assert catalogue.topics(TOPIC_PREFIX) == ("trialscribe.job.v1",)
    assert catalogue.resolve(JOB_REQUESTED_EVENT_TYPE, JOB_EVENT_VERSION).domain == "job"


def test_a_job_request_survives_the_round_trip_through_kafka_bytes() -> None:
    original = envelope()

    restored = EventEnvelope.from_bytes(original.to_bytes())
    decoded = registry().decode(restored)

    assert isinstance(decoded, JobRequested)
    assert decoded == payload()
    assert restored.partition_key() == str(JOB_ID).encode("utf-8")


def test_a_field_added_by_a_newer_producer_is_ignored_rather_than_rejected() -> None:
    body = json.loads(envelope().to_bytes())
    body["payload"]["priority"] = "high"

    decoded = registry().decode(
        EventEnvelope.from_bytes(json.dumps(body).encode("utf-8"))
    )

    assert isinstance(decoded, JobRequested)
    assert decoded.kind == "probe"


def test_a_request_missing_its_job_identity_is_a_contract_failure() -> None:
    body = json.loads(envelope().to_bytes())
    del body["payload"]["job_id"]

    with pytest.raises(EventContractError):
        registry().decode(
            EventEnvelope.from_bytes(json.dumps(body).encode("utf-8"))
        )


def test_a_request_defaults_to_its_first_attempt_and_no_parameters() -> None:
    minimal = JobRequested(
        job_id=JOB_ID,
        kind="probe",
        organization_id=ORGANIZATION_ID,
        requested_by_account_id=ACCOUNT_ID,
    )

    assert minimal.attempt == 1
    assert minimal.parameters == {}
    assert minimal.conversation_id is None


def test_registering_the_job_contracts_twice_is_refused() -> None:
    catalogue = registry()

    with pytest.raises(EventRegistrationError):
        register_job_events(catalogue)
