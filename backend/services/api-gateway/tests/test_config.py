import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from trialscribe_gateway.config import GatewaySettings


def public_key_b64() -> str:
    public_key = Ed25519PrivateKey.generate().public_key()
    raw_key = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw_key).decode()


def valid_values() -> dict[str, object]:
    return {
        "gateway_auth_service_url": "http://127.0.0.1:8001",
        "gateway_user_service_url": "http://127.0.0.1:8002",
        "gateway_ai_service_url": "http://127.0.0.1:8003",
        "gateway_worker_service_url": "http://127.0.0.1:8004",
        "gateway_cors_origins": ["http://localhost:5173"],
        "gateway_upstream_connect_timeout_seconds": 2,
        "gateway_upstream_read_timeout_seconds": 60,
        "gateway_upstream_write_timeout_seconds": 60,
        "gateway_upstream_pool_timeout_seconds": 2,
        "auth_jwt_public_key_b64": public_key_b64(),
        "auth_jwt_issuer": "trialscribe-auth",
        "auth_jwt_audience": "trialscribe-api",
    }


def valid_settings(**overrides: object) -> GatewaySettings:
    values = valid_values()
    values.update(overrides)
    return GatewaySettings(**values)


def test_valid_settings_normalize_runtime_values() -> None:
    settings = valid_settings()

    assert settings.service_url("auth") == "http://127.0.0.1:8001"
    assert settings.service_url("user") == "http://127.0.0.1:8002"
    assert settings.cors_origins() == ["http://localhost:5173"]
    assert settings.verification_key() is not None


def test_uv_env_file_cors_representation_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = valid_values()
    values.pop("gateway_cors_origins")
    monkeypatch.setenv("GATEWAY_CORS_ORIGINS", "[http://localhost:5173]")

    settings = GatewaySettings(**values)

    assert settings.cors_origins() == ["http://localhost:5173"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gateway_auth_service_url", "ftp://internal.example.com"),
        ("gateway_user_service_url", "not-a-url"),
        ("gateway_cors_origins", ["*"]),
        ("gateway_cors_origins", ["https://app.example.com/path"]),
        ("gateway_cors_origins", []),
        (
            "gateway_cors_origins",
            ["https://app.example.com", "https://app.example.com"],
        ),
        ("auth_jwt_public_key_b64", "not-a-key"),
        ("auth_jwt_issuer", " "),
        ("auth_jwt_audience", ""),
        ("gateway_upstream_connect_timeout_seconds", 0),
        ("gateway_upstream_read_timeout_seconds", -1),
        ("gateway_upstream_write_timeout_seconds", 0),
        ("gateway_upstream_pool_timeout_seconds", -1),
    ],
)
def test_invalid_public_contract_values_are_rejected(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        valid_settings(**{field: value})


def test_validation_errors_hide_submitted_values() -> None:
    secret_value = "https://internal.example.com/secret-path"

    with pytest.raises(ValidationError) as captured:
        valid_settings(gateway_auth_service_url=secret_value)

    assert secret_value not in str(captured.value)
