"""AI-engine exceptions that are translated at the HTTP boundary."""


class AIEngineError(Exception):
    """Base class for expected AI-engine failures."""


class SessionNotFoundError(AIEngineError):
    """The requested session does not exist."""


class SessionExpiredError(AIEngineError):
    """The requested session has expired."""


class InvalidJsonFileError(AIEngineError):
    """Uploaded trial JSON is invalid."""


class UnsupportedDocumentError(AIEngineError):
    """An uploaded supporting document type is unsupported."""


class TrialProcessingError(AIEngineError):
    """Trial data could not be processed."""


class DocumentUploadError(AIEngineError):
    """Supporting documents could not be stored."""


class MissingTrialDataError(AIEngineError):
    """Report generation requires trial data."""


class MissingDocumentsError(AIEngineError):
    """Report generation requires supporting documents."""


class ReportGenerationError(AIEngineError):
    """A report could not be generated."""
