"""Event backbone enums."""

from enum import StrEnum


class DeadLetterReason(StrEnum):
    """Why a Kafka record was routed to a dead-letter topic."""

    UNDECODABLE = "undecodable"
    UNKNOWN_EVENT_TYPE = "unknown_event_type"
    CONTRACT_MISMATCH = "contract_mismatch"
    HANDLER_FAILED = "handler_failed"
