"""API-gateway exceptions that are translated at the HTTP boundary."""


class GatewayServiceError(Exception):
    """Base class for expected API-gateway failures."""
