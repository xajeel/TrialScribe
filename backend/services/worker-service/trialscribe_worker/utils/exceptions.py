"""Worker-service exceptions that are translated at the HTTP boundary."""


class WorkerServiceError(Exception):
    """Base class for expected worker-service failures."""


class JobNotFoundError(WorkerServiceError):
    """No job with that identity exists inside the requesting organization."""


class JobAlreadyFinishedError(WorkerServiceError):
    """A job that already reached its outcome cannot be changed."""


class InvalidJobInputError(WorkerServiceError):
    """A job request carried input the worker refuses to accept."""


class UnsupportedJobKindError(WorkerServiceError):
    """No pipeline in this worker serves the requested kind of work."""


class JobCancelledError(WorkerServiceError):
    """A running job was asked to stop and did so at its next checkpoint."""


class ProbeFaultInjected(WorkerServiceError):
    """The probe pipeline failed on purpose, because it was asked to."""


class JobAttemptFailedError(WorkerServiceError):
    """One attempt failed while more remain, so the record must be redelivered."""


class ProviderTimeoutError(WorkerServiceError):
    """A provider call did not finish before its configured deadline."""


class ProviderRateLimitedError(WorkerServiceError):
    """A provider refused the call because too many are already in flight."""


class ProviderUnavailableError(WorkerServiceError):
    """A provider was down, overloaded, or returned a retryable server error."""


class ProviderCircuitOpenError(WorkerServiceError):
    """The circuit breaker is open, so the provider is not called."""


class ProviderConfigError(WorkerServiceError):
    """The provider, model, or pricing configuration cannot be used."""


class DocumentExtractionError(WorkerServiceError):
    """A stored file could not be turned into indexable text."""
