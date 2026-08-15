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

CONTENT_TYPE_OPTIONS_HEADER = "X-Content-Type-Options"
CONTENT_TYPE_OPTIONS_VALUE = "nosniff"
FRAME_OPTIONS_HEADER = "X-Frame-Options"
FRAME_OPTIONS_VALUE = "DENY"
REFERRER_POLICY_HEADER = "Referrer-Policy"
REFERRER_POLICY_VALUE = "no-referrer"
CACHE_CONTROL_HEADER = "Cache-Control"
CACHE_CONTROL_VALUE = "no-store"
CONTENT_SECURITY_POLICY_HEADER = "Content-Security-Policy"
CONTENT_SECURITY_POLICY_VALUE = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
)
DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})
DOCS_CONTENT_SECURITY_POLICY_VALUE = (
    "default-src 'none'; "
    "script-src https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)
PERMISSIONS_POLICY_HEADER = "Permissions-Policy"
PERMISSIONS_POLICY_VALUE = "camera=(), microphone=(), geolocation=()"

TOO_MANY_REQUESTS_DETAIL = "Too many requests"
RETRY_AFTER_HEADER = "Retry-After"
RATE_LIMIT_FAMILY_AUTH = "auth"
RATE_LIMIT_FAMILY_API = "api"
RATE_LIMIT_EXEMPT_PATHS = frozenset(
    {"/health/live", "/health/ready", "/metrics"}
)
RATE_LIMIT_MAX_KEYS = 10_000
RATE_LIMIT_HMAC_MIN_LENGTH = 16

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
