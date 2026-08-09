"""Event backbone exceptions that never reveal message content."""


class EventError(RuntimeError):
    """A failure inside the shared event backbone."""


class InvalidEventError(EventError):
    """A record could not be read as an event envelope."""


class UnknownEventTypeError(EventError):
    """No registration exists for an event type and version."""


class EventContractError(EventError):
    """An event payload does not match its registered contract."""


class EventRegistrationError(EventError):
    """An event type and version was registered more than once."""


class EventPublishError(EventError):
    """An event could not be handed to the broker."""
