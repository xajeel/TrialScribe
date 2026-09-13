"""Secret generation and one-way storage for organization invitations."""

import hashlib
import secrets
from urllib.parse import urlencode


def generate_invitation_token() -> str:
    """Return a URL-safe invitation secret with 256 bits of randomness."""

    return secrets.token_urlsafe(32)


def hash_invitation_token(token: str) -> str:
    """Return the one-way database representation of an invitation token."""

    return hashlib.sha256(token.encode()).hexdigest()


def build_invitation_url(base_url: str, token: str) -> str:
    """Put an invitation secret into the configured acceptance URL once."""

    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': token})}"
