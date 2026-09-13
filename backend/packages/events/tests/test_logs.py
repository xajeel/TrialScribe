import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.logs import JsonLogFormatter, event_context, get_event_logger

EVENT_ID = UUID("00000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000000003")


def envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=EVENT_ID,
        event_type="job.generation.requested",
        event_version=1,
        occurred_at=datetime(2026, 8, 8, 12, 30, 0, tzinfo=UTC),
        organization_id=ORGANIZATION_ID,
        subject="job-1",
        correlation_id=CORRELATION_ID,
        producer="ai-engine",
        payload={"section_code": "do-not-print"},
    )


def format_record(context: dict[str, object]) -> dict[str, object]:
    record = logging.LogRecord(
        name="trialscribe_events.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="event.dead_lettered",
        args=(),
        exc_info=None,
    )
    record.event_context = context  # type: ignore[attr-defined]
    return json.loads(JsonLogFormatter().format(record))


def test_context_carries_only_allow_listed_envelope_facts() -> None:
    context = event_context(envelope(), topic="trialscribe.job.v1", attempt=2, reason="handler_failed")

    assert context == {
        "event_id": str(EVENT_ID),
        "event_type": "job.generation.requested",
        "event_version": 1,
        "organization_id": str(ORGANIZATION_ID),
        "topic": "trialscribe.job.v1",
        "attempt": 2,
        "reason": "handler_failed",
    }
    assert "do-not-print" not in json.dumps(context)
    assert "subject" not in context
    assert "payload" not in context


def test_context_omits_absent_optional_fields() -> None:
    assert event_context(topic="trialscribe.job.v1") == {"topic": "trialscribe.job.v1"}
    assert event_context() == {}


def test_formatter_emits_one_json_object_per_record() -> None:
    document = format_record(event_context(envelope(), partition=0, offset=17))

    assert document["level"] == "warning"
    assert document["message"] == "event.dead_lettered"
    assert document["partition"] == 0
    assert document["offset"] == 17
    assert document["event_id"] == str(EVENT_ID)


def test_formatter_drops_any_field_outside_the_allow_list() -> None:
    document = format_record(
        {
            "topic": "trialscribe.job.v1",
            "payload": "do-not-print",
            "prompt": "system secret prompt",
            "api_key": "sk-secret",
            "evidence": "cited passage",
            "password": "hunter2",
        }
    )

    assert "payload" not in document
    assert "prompt" not in document
    assert "api_key" not in document
    assert "evidence" not in document
    assert "password" not in document
    assert "do-not-print" not in json.dumps(document)
    assert "sk-secret" not in json.dumps(document)
    assert "hunter2" not in json.dumps(document)


def test_logger_writes_structured_json_without_duplicating_to_the_root() -> None:
    logger = get_event_logger("trialscribe_events.test_logger")

    assert logger.propagate is False
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, JsonLogFormatter)
    assert get_event_logger("trialscribe_events.test_logger") is logger
    assert len(logger.handlers) == 1
