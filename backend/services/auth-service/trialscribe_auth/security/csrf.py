"""Session-bound signed double-submit CSRF tokens."""

import base64
import hashlib
import hmac
import secrets
from uuid import UUID


def _signature(session_id: UUID, nonce: str, key: bytes) -> str:
    message = f"csrf:{session_id}:{nonce}".encode()
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def generate_csrf_token(session_id: UUID, key: bytes) -> str:
    """Create a random token whose signature is bound to one session."""

    nonce = secrets.token_urlsafe(32)
    return f"{nonce}.{_signature(session_id, nonce, key)}"


def validate_csrf_token(
    session_id: UUID,
    cookie_token: str,
    header_token: str,
    key: bytes,
) -> bool:
    """Validate double-submit equality and the session-bound signature."""

    if not hmac.compare_digest(cookie_token, header_token):
        return False
    try:
        nonce, supplied_signature = cookie_token.split(".", maxsplit=1)
    except ValueError:
        return False
    if not nonce or not supplied_signature:
        return False
    return hmac.compare_digest(
        supplied_signature,
        _signature(session_id, nonce, key),
    )
