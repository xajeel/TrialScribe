"""Topic naming and the shared catalogue of event types."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ValidationError

from trialscribe_events.envelope import EventEnvelope
from trialscribe_events.utils.constant import (
    CONTRACT_MISMATCH_MESSAGE,
    DEAD_LETTER_SUFFIX,
    DUPLICATE_REGISTRATION_MESSAGE,
    UNKNOWN_EVENT_TYPE_MESSAGE,
)
from trialscribe_events.utils.exceptions import (
    EventContractError,
    EventRegistrationError,
    UnknownEventTypeError,
)


def topic_for(prefix: str, domain: str, version: int) -> str:
    """Name the topic that carries one major version of one domain."""

    return f"{prefix}.{domain}.v{version}"


def dead_letter_topic(topic: str) -> str:
    """Name the companion topic that holds records a consumer could not handle."""

    return f"{topic}.{DEAD_LETTER_SUFFIX}"


@dataclass(frozen=True, slots=True)
class RegisteredEvent:
    """One event type at one major version, and the payload it must carry."""

    event_type: str
    version: int
    domain: str
    payload_model: type[BaseModel]


class EventRegistry:
    """Map event types onto their topics and their payload contracts."""

    def __init__(self) -> None:
        self._registrations: dict[tuple[str, int], RegisteredEvent] = {}

    def register(
        self,
        event_type: str,
        version: int,
        domain: str,
        payload_model: type[BaseModel],
    ) -> RegisteredEvent:
        """Record one event type; registering the same version twice is a defect."""

        key = (event_type, version)
        if key in self._registrations:
            raise EventRegistrationError(DUPLICATE_REGISTRATION_MESSAGE)
        registration = RegisteredEvent(
            event_type=event_type,
            version=version,
            domain=domain,
            payload_model=payload_model,
        )
        self._registrations[key] = registration
        return registration

    def resolve(self, event_type: str, version: int) -> RegisteredEvent:
        """Look up a registration, refusing anything this service does not know."""

        registration = self._registrations.get((event_type, version))
        if registration is None:
            raise UnknownEventTypeError(UNKNOWN_EVENT_TYPE_MESSAGE)
        return registration

    def topics(self, prefix: str) -> tuple[str, ...]:
        """Return every topic this registry publishes to or subscribes to."""

        names = {
            topic_for(prefix, registration.domain, registration.version)
            for registration in self._registrations.values()
        }
        return tuple(sorted(names))

    def topic_of(self, prefix: str, envelope: EventEnvelope) -> str:
        """Return the topic an envelope belongs on."""

        registration = self.resolve(envelope.event_type, envelope.event_version)
        return topic_for(prefix, registration.domain, registration.version)

    def build(
        self,
        *,
        event_type: str,
        version: int,
        organization_id: UUID,
        subject: str,
        correlation_id: UUID,
        producer: str,
        payload: BaseModel,
        causation_id: UUID | None = None,
        occurred_at: datetime | None = None,
    ) -> EventEnvelope:
        """Wrap a registered payload in the shared envelope."""

        registration = self.resolve(event_type, version)
        if not isinstance(payload, registration.payload_model):
            raise EventContractError(CONTRACT_MISMATCH_MESSAGE)
        return EventEnvelope(
            event_type=event_type,
            event_version=version,
            occurred_at=occurred_at or datetime.now(UTC),
            organization_id=organization_id,
            subject=subject,
            correlation_id=correlation_id,
            causation_id=causation_id,
            producer=producer,
            payload=payload.model_dump(mode="json"),
        )

    def decode(self, envelope: EventEnvelope) -> BaseModel:
        """Validate an envelope's payload against its registered contract."""

        registration = self.resolve(envelope.event_type, envelope.event_version)
        try:
            return registration.payload_model.model_validate(envelope.payload)
        except ValidationError:
            raise EventContractError(CONTRACT_MISMATCH_MESSAGE) from None
