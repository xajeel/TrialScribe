"""Worker-service exceptions that are translated at the HTTP boundary."""


class WorkerServiceError(Exception):
    """Base class for expected worker-service failures."""
