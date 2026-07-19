"""Stable auth-service constants."""

APP_TITLE = "TrialScribe Auth"
APP_VERSION = "0.1.0"
SERVICE_NAME = "auth-service"
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
MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128

REFRESH_COOKIE = "trialscribe_refresh"
CSRF_COOKIE = "trialscribe_csrf"
AUTH_COOKIE_PATH = "/v1/auth"

INVALID_AUTHENTICATION_DETAIL = "Invalid authentication credentials"
INVALID_ACCOUNT_DETAIL = "Invalid account input"
ACCOUNT_CONFLICT_DETAIL = "Account already exists"
AUTHENTICATION_UNAVAILABLE_DETAIL = "Authentication service unavailable"
TOO_MANY_ATTEMPTS_DETAIL = "Too many authentication attempts"
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable"

FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""
