"""Stable API-gateway constants."""

APP_TITLE = "TrialScribe Gateway"
APP_VERSION = "0.1.0"
SERVICE_NAME = "api-gateway"
LIVENESS_STATUS = "ok"
READINESS_STATUS = "ready"

ACCESS_TOKEN_ALGORITHM = "EdDSA"
ACCESS_TOKEN_REQUIRED_CLAIMS = (
    "sub",
    "iss",
    "aud",
    "iat",
    "nbf",
    "exp",
    "jti",
    "type",
)

AUTH_ROUTE_PREFIX = "/v1/auth"
ORGANIZATIONS_ROUTE_PREFIX = "/v1/organizations"
INVITATIONS_ROUTE_PREFIX = "/v1/organization-invitations"
AI_ROUTE_PREFIX = "/v1/ai"
JOBS_ROUTE_PREFIX = "/v1/jobs"

AUTHORIZATION_HEADER = "Authorization"
REQUEST_ID_HEADER = "X-Request-ID"
ORGANIZATION_ID_HEADER = "X-Organization-ID"
INTERNAL_ACCOUNT_ID_HEADER = "X-TrialScribe-Account-ID"
INTERNAL_ORGANIZATION_ID_HEADER = "X-TrialScribe-Organization-ID"

INVALID_AUTHENTICATION_DETAIL = "Invalid authentication credentials"
INVALID_ORGANIZATION_DETAIL = "Invalid organization context"
ORGANIZATION_ACCESS_DENIED_DETAIL = "Organization access denied"
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable"
UPSTREAM_TIMEOUT_DETAIL = "Service request timed out"

HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
