"""Structured JSON logging that can never carry event content."""

import json
import logging
from typing import Any
from uuid import UUID

from trialscribe_events.envelope import EventEnvelope

CONTEXT_FIELDS = (
    "event_id",
    "event_type",
    "event_version",
    "organization_id",
    "topic",
    "partition",
    "offset",
    "attempt",
    "reason",
)


class JsonLogFormatter(logging.Formatter):
    """Render one JSON object per record, using allow-listed context only."""

    def format(self, record: logging.LogRecord) -> str:
        document: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "event_context", None)
        if isinstance(context, dict):
            document.update(
                {key: value for key, value in context.items() if key in CONTEXT_FIELDS}
            )
        return json.dumps(document, separators=(",", ":"), sort_keys=True)


def get_event_logger(name: str) -> logging.Logger:
    """Return a logger that writes structured JSON and never plain text."""

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def event_context(
    envelope: EventEnvelope | None = None,
    *,
    topic: str | None = None,
    partition: int | None = None,
    offset: int | None = None,
    attempt: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Assemble log fields from an allow-list; payload content can never enter."""

    context: dict[str, Any] = {}
    if envelope is not None:
        context.update(
            event_id=str(envelope.event_id),
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            organization_id=str(envelope.organization_id),
        )
    optional: dict[str, Any] = {
        "topic": topic,
        "partition": partition,
        "offset": offset,
        "attempt": attempt,
        "reason": reason,
    }
    context.update({key: value for key, value in optional.items() if value is not None})
    return {
        key: (str(value) if isinstance(value, UUID) else value)
        for key, value in context.items()
    }
