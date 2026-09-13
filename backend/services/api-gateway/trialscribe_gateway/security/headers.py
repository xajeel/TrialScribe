"""Browser-safety headers for gateway responses."""

from starlette.responses import Response

from trialscribe_gateway.utils.constant import (
    CACHE_CONTROL_HEADER,
    CACHE_CONTROL_VALUE,
    CONTENT_SECURITY_POLICY_HEADER,
    CONTENT_SECURITY_POLICY_VALUE,
    CONTENT_TYPE_OPTIONS_HEADER,
    CONTENT_TYPE_OPTIONS_VALUE,
    FRAME_OPTIONS_HEADER,
    FRAME_OPTIONS_VALUE,
    PERMISSIONS_POLICY_HEADER,
    PERMISSIONS_POLICY_VALUE,
    REFERRER_POLICY_HEADER,
    REFERRER_POLICY_VALUE,
)


def apply_secure_headers(
    response: Response,
    *,
    content_security_policy: str = CONTENT_SECURITY_POLICY_VALUE,
) -> None:
    """Stamp a response with the public-edge safety headers."""

    response.headers[CONTENT_TYPE_OPTIONS_HEADER] = CONTENT_TYPE_OPTIONS_VALUE
    response.headers[FRAME_OPTIONS_HEADER] = FRAME_OPTIONS_VALUE
    response.headers[REFERRER_POLICY_HEADER] = REFERRER_POLICY_VALUE
    response.headers[CACHE_CONTROL_HEADER] = CACHE_CONTROL_VALUE
    response.headers[CONTENT_SECURITY_POLICY_HEADER] = content_security_policy
    response.headers[PERMISSIONS_POLICY_HEADER] = PERMISSIONS_POLICY_VALUE
