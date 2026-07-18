import base64
import secrets
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from trialscribe_auth.config import AuthSettings


def encoded_key_pair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return (
        base64.b64encode(private_bytes).decode(),
        base64.b64encode(public_bytes).decode(),
    )


def settings_values() -> dict[str, Any]:
    private_key, public_key = encoded_key_pair()
    return {
        "auth_jwt_private_key_b64": private_key,
        "auth_jwt_public_key_b64": public_key,
        "auth_jwt_issuer": "trialscribe-auth",
        "auth_jwt_audience": "trialscribe-api",
        "auth_access_token_ttl_seconds": 900,
        "auth_refresh_token_ttl_seconds": 2_592_000,
        "auth_cookie_secure": False,
        "auth_hmac_secret": secrets.token_urlsafe(32),
        "auth_login_attempt_limit": 5,
        "auth_login_window_seconds": 300,
        "redis_url": "redis://:private-password@localhost:6379/0",
    }


def test_valid_settings_build_matching_keys_and_redact_secrets() -> None:
    values = settings_values()
    settings = AuthSettings(**values)

    assert settings.signing_key().public_key() == settings.verification_key()
    assert settings.redis_connection_url() == values["redis_url"]
    assert settings.hmac_key() == values["auth_hmac_secret"].encode()
    representation = repr(settings)
    assert values["auth_jwt_private_key_b64"] not in representation
    assert values["redis_url"] not in representation
    assert values["auth_hmac_secret"] not in representation


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auth_access_token_ttl_seconds", 0),
        ("auth_refresh_token_ttl_seconds", -1),
        ("auth_login_attempt_limit", 0),
        ("auth_login_window_seconds", 0),
    ],
)
def test_durations_and_limits_must_be_positive(field: str, value: int) -> None:
    values = settings_values()
    values[field] = value

    with pytest.raises(ValidationError):
        AuthSettings(**values)


def test_refresh_lifetime_must_exceed_access_lifetime() -> None:
    values = settings_values()
    values["auth_refresh_token_ttl_seconds"] = 900

    with pytest.raises(ValidationError):
        AuthSettings(**values)


def test_key_pair_must_match_without_exposing_private_key() -> None:
    values = settings_values()
    private_value = values["auth_jwt_private_key_b64"]
    _, values["auth_jwt_public_key_b64"] = encoded_key_pair()

    with pytest.raises(ValidationError) as captured:
        AuthSettings(**values)

    assert private_value not in str(captured.value)


@pytest.mark.parametrize("value", ["", "not-base64", base64.b64encode(b"short").decode()])
def test_private_key_must_be_valid_and_redacted(value: str) -> None:
    values = settings_values()
    values["auth_jwt_private_key_b64"] = value

    with pytest.raises(ValidationError) as captured:
        AuthSettings(**values)

    assert value not in str(captured.value) or not value


@pytest.mark.parametrize(
    "value",
    ["", "short", "change-me-local-authentication-secret"],
)
def test_hmac_secret_rejects_short_or_placeholder_values(value: str) -> None:
    values = settings_values()
    values["auth_hmac_secret"] = value

    with pytest.raises(ValidationError) as captured:
        AuthSettings(**values)

    assert value not in str(captured.value) or not value


@pytest.mark.parametrize(
    "value",
    ["https://localhost:6379/0", "redis:///0", "redis://localhost:6379/0"],
)
def test_redis_url_requires_redis_scheme_host_and_authentication(value: str) -> None:
    values = settings_values()
    values["redis_url"] = value

    with pytest.raises(ValidationError) as captured:
        AuthSettings(**values)

    assert value not in str(captured.value)


def test_missing_configuration_does_not_echo_other_secret_inputs() -> None:
    private_key, _ = encoded_key_pair()

    with pytest.raises(ValidationError) as captured:
        AuthSettings(auth_jwt_private_key_b64=private_key)

    assert private_key not in str(captured.value)
