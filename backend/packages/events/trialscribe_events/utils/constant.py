"""Stable event backbone constants."""

CONTENT_TYPE = "application/json"
DEAD_LETTER_SUFFIX = "dlq"
EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
MAX_SUBJECT_LENGTH = 200
MAX_PRODUCER_LENGTH = 100
MAX_EVENT_TYPE_LENGTH = 200
MAX_CONSUMER_GROUP_LENGTH = 200

JOB_EVENT_DOMAIN = "job"
JOB_REQUESTED_EVENT_TYPE = "job.generation.requested"
JOB_EVENT_VERSION = 1
MAX_JOB_KIND_LENGTH = 50
MAX_JOB_PARAMETERS_BYTES = 16384

EVENT_ID_HEADER = "x-trialscribe-event-id"
EVENT_TYPE_HEADER = "x-trialscribe-event-type"
EVENT_VERSION_HEADER = "x-trialscribe-event-version"
CONTENT_TYPE_HEADER = "content-type"
DEAD_LETTER_REASON_HEADER = "x-trialscribe-dead-letter-reason"

INVALID_ENVELOPE_MESSAGE = "event envelope is not valid"
UNKNOWN_EVENT_TYPE_MESSAGE = "event type is not registered"
CONTRACT_MISMATCH_MESSAGE = "event payload does not match its contract"
DUPLICATE_REGISTRATION_MESSAGE = "event type and version is already registered"
PUBLISH_FAILURE_MESSAGE = "event could not be published"

MAX_OUTBOX_TOPIC_LENGTH = 200
DEFAULT_OUTBOX_BATCH_SIZE = 100
