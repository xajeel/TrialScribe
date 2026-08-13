"""Worker-service enums."""

from enum import StrEnum


class JobStatus(StrEnum):
    """Where a background job currently stands."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        """Return True once no further work can change this job's outcome."""

        return self in TERMINAL_JOB_STATUSES


class JobErrorCode(StrEnum):
    """Why a background job did not succeed, in bounded terms safe to publish."""

    HANDLER_FAILED = "handler_failed"
    UNSUPPORTED_KIND = "unsupported_kind"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
)
CLAIMABLE_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING}
)


class JobKind(StrEnum):
    """The kinds of background work this worker knows how to run."""

    PROBE = "probe"
    PROVIDER_PROBE = "provider_probe"


class ProviderName(StrEnum):
    """Which backend the gateway is configured to call."""

    FAKE = "fake"
    DEEPSEEK = "deepseek"
    FASTEMBED = "fastembed"


class ProviderOperation(StrEnum):
    """Whether a metered call was a chat completion or an embedding."""

    CHAT = "chat"
    EMBED = "embed"


class ProviderOutcome(StrEnum):
    """How a single provider attempt ended, in bounded terms safe to store."""

    SUCCEEDED = "succeeded"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"
    ERROR = "error"
