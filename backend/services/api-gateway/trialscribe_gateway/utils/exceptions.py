"""API-gateway exceptions that are translated at the HTTP boundary."""


class GatewayServiceError(Exception):
    """Base class for expected API-gateway failures."""


class InvalidAccessTokenError(GatewayServiceError, ValueError):
    """An access token failed the public authentication contract."""


class UpstreamUnavailableError(GatewayServiceError, ConnectionError):
    """A configured upstream service could not be reached."""


class UpstreamTimeoutError(GatewayServiceError, TimeoutError):
    """A configured upstream service exceeded a gateway timeout."""
