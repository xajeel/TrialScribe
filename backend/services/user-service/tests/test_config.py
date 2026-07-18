import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from trialscribe_user.config import UserSettings


def public_key_b64() -> str:
    key = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(key).decode()


def valid_values() -> dict[str, object]:
    return {
        "auth_jwt_public_key_b64": public_key_b64(),
        "auth_jwt_issuer": "trialscribe-auth",
        "auth_jwt_audience": "trialscribe-api",
        "user_invitation_ttl_seconds": 604800,
        "user_invitation_accept_url": "https://app.example.com/invitations/accept",
    }


def test_settings_hold_only_public_verification_and_invitation_values() -> None:
    settings = UserSettings(**valid_values())

    assert settings.verification_key() is not None
    assert settings.user_invitation_ttl_seconds == 604800
    assert settings.invitation_accept_url().startswith("https://app.example.com/")
    assert "auth_jwt_private_key_b64" not in UserSettings.model_fields


@pytest.mark.parametrize("key", ["not-base64", base64.b64encode(b"short").decode()])
def test_public_key_must_be_valid_ed25519_material(key: str) -> None:
    values = valid_values()
    values["auth_jwt_public_key_b64"] = key

    with pytest.raises(ValidationError) as error:
        UserSettings(**values)

    assert key not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auth_jwt_issuer", ""),
        ("auth_jwt_audience", "  "),
        ("user_invitation_ttl_seconds", 0),
        ("user_invitation_accept_url", "/invitations/accept"),
        ("user_invitation_accept_url", "ftp://example.com/invitations/accept"),
    ],
)
def test_invalid_public_contract_values_are_rejected(field: str, value: object) -> None:
    values = valid_values()
    values[field] = value

    with pytest.raises(ValidationError):
        UserSettings(**values)


def test_settings_load_the_documented_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in valid_values().items():
        monkeypatch.setenv(key.upper(), str(value))

    settings = UserSettings()

    assert settings.auth_jwt_issuer == "trialscribe-auth"
    assert settings.user_invitation_ttl_seconds == 604800
