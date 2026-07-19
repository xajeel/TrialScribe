"""AI-engine exceptions that are translated at the HTTP boundary."""


class AIEngineError(Exception):
    """Base class for expected AI-engine failures."""


class InvalidConversationInputError(AIEngineError):
    """Conversation input failed a domain rule."""


class ConversationNotFoundError(AIEngineError):
    """The conversation is absent or inaccessible to the caller."""


class ConversationPermissionDeniedError(AIEngineError):
    """The caller cannot perform an owner-only action."""


class ConversationArchivedError(AIEngineError):
    """An archived conversation cannot accept new messages."""


class CollaboratorConflictError(AIEngineError):
    """A requested collaborator is not a valid organization member."""


class InvalidCursorError(AIEngineError):
    """A pagination cursor could not be validated."""


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
