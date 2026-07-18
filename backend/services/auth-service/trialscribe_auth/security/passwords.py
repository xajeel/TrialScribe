"""Argon2id password hashing and verification primitives."""

import secrets
from functools import lru_cache

from pwdlib import PasswordHash

MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128

_PASSWORD_HASH = PasswordHash.recommended()


class InvalidPasswordError(ValueError):
    """A password does not satisfy the public account contract."""


def validate_password(password: str) -> str:
    """Accept passphrases in the supported length range without truncation."""

    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters"
        )
    return password


def hash_password(password: str) -> str:
    """Validate and hash a password with the recommended Argon2id settings."""

    return _PASSWORD_HASH.hash(validate_password(password))


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a password matches, treating malformed hashes as invalid."""

    try:
        return _PASSWORD_HASH.verify(password, password_hash)
    except (TypeError, ValueError):
        return False


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return _PASSWORD_HASH.hash(secrets.token_urlsafe(32))


def dummy_verify(password: str) -> None:
    """Spend one normal verification cost when no account hash is available."""

    _PASSWORD_HASH.verify(password, _dummy_password_hash())
