"""Auth-service exceptions that never define HTTP response bodies."""


class InvalidPasswordError(ValueError):
    """A password does not satisfy the public account contract."""


class RateLimitUnavailableError(RuntimeError):
    """Login throttling cannot currently be enforced."""


class InvalidAccessTokenError(ValueError):
    """An access token failed the public authentication contract."""


class DuplicateAccountError(RuntimeError):
    """A normalized email already belongs to an account."""


class InvalidAccountInput(ValueError):
    """Registration input does not meet the public account contract."""


class AccountConflictError(RuntimeError):
    """An account cannot be created for the supplied identity."""


class DependencyUnavailableError(RuntimeError):
    """A required auth-service dependency is unavailable."""
