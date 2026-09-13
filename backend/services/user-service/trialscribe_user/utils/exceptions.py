"""User-service exceptions that never define HTTP response bodies."""


class InvalidAccessTokenError(ValueError):
    """An access token failed the public authentication contract."""


class InvalidInvitationInput(ValueError):
    """Invitation input does not meet the public contract."""


class InvitationConflictError(RuntimeError):
    """An invitation conflicts with membership or invitation state."""


class InvalidInvitationError(ValueError):
    """An invitation token is unusable without revealing why."""


class OrganizationNotFoundError(LookupError):
    """The organization is not visible to the current account."""


class PermissionDeniedError(PermissionError):
    """The current organization role does not allow an action."""


class InvalidOrganizationInput(ValueError):
    """Organization input does not meet the public contract."""


class MembershipConflictError(RuntimeError):
    """A membership change would violate organization continuity."""


class DuplicateInvitationError(RuntimeError):
    """A live invitation or token hash conflicts with persisted state."""


class DuplicateMembershipError(RuntimeError):
    """An account already belongs to an organization."""
