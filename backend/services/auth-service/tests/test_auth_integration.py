"""Live authentication lifecycle checks driven by scripts/check_authentication.py."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from trialscribe_auth.api.app import app
from trialscribe_auth.config import AuthSettings
from trialscribe_auth.security.tokens import AccessTokenCodec

pytestmark = pytest.mark.integration

INTEGRATION_ENABLED = os.getenv("TRIALSCRIBE_AUTH_INTEGRATION") == "1"
PHASE = os.getenv("TRIALSCRIBE_AUTH_PHASE", "")
STATE_FILE = Path(os.getenv("TRIALSCRIBE_AUTH_STATE_FILE", "/nonexistent"))
PASSWORD = os.getenv("TRIALSCRIBE_AUTH_TEST_PASSWORD", "")
EMAIL = "persistent.researcher@example.com"
RATE_EMAIL = "restart-rate-limit@example.com"


def require_phase(expected: str) -> None:
    if not INTEGRATION_ENABLED or PHASE != expected:
        pytest.skip(f"requires authentication integration {expected} phase")


def select_session(client: TestClient, refresh_token: str, csrf_token: str) -> None:
    client.cookies.clear()
    client.cookies.set(
        "trialscribe_refresh",
        refresh_token,
        domain="testserver.local",
        path="/v1/auth",
    )
    client.cookies.set(
        "trialscribe_csrf",
        csrf_token,
        domain="testserver.local",
        path="/v1/auth",
    )


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200
    refresh_token = client.cookies.get("trialscribe_refresh")
    csrf_token = client.cookies.get("trialscribe_csrf")
    assert refresh_token is not None
    assert csrf_token is not None
    return {
        "access_token": response.json()["access_token"],
        "refresh_token": refresh_token,
        "csrf_token": csrf_token,
    }


def assert_invalid(response: Any) -> None:
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}


def test_prepare_complete_authentication_lifecycle() -> None:
    require_phase("prepare")
    assert len(PASSWORD) >= 15

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={"email": "Persistent.Researcher@Example.COM", "password": PASSWORD},
        )
        assert registration.status_code == 201
        account_id = registration.json()["id"]
        duplicate = client.post(
            "/v1/auth/register",
            json={"email": EMAIL, "password": PASSWORD},
        )
        assert duplicate.status_code == 409

        unknown = client.post(
            "/v1/auth/login",
            json={"email": "unknown@example.com", "password": PASSWORD},
        )
        wrong = client.post(
            "/v1/auth/login",
            json={"email": EMAIL, "password": f"{PASSWORD}wrong"},
        )
        assert_invalid(unknown)
        assert_invalid(wrong)

        first = login(client)
        current = client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {first['access_token']}"},
        )
        assert current.status_code == 200
        assert current.json()["email"] == EMAIL

        second = login(client)
        select_session(client, first["refresh_token"], first["csrf_token"])
        rotated = client.post(
            "/v1/auth/refresh",
            headers={"X-CSRF-Token": first["csrf_token"]},
        )
        assert rotated.status_code == 200
        replacement_refresh = client.cookies.get("trialscribe_refresh")
        replacement_csrf = client.cookies.get("trialscribe_csrf")
        assert replacement_refresh and replacement_csrf

        select_session(client, first["refresh_token"], first["csrf_token"])
        assert_invalid(
            client.post(
                "/v1/auth/refresh",
                headers={"X-CSRF-Token": first["csrf_token"]},
            )
        )
        select_session(client, replacement_refresh, replacement_csrf)
        assert_invalid(
            client.post(
                "/v1/auth/refresh",
                headers={"X-CSRF-Token": replacement_csrf},
            )
        )

        select_session(client, second["refresh_token"], second["csrf_token"])
        assert client.post(
            "/v1/auth/logout",
            headers={"X-CSRF-Token": second["csrf_token"]},
        ).status_code == 204
        select_session(client, second["refresh_token"], second["csrf_token"])
        assert_invalid(
            client.post(
                "/v1/auth/refresh",
                headers={"X-CSRF-Token": second["csrf_token"]},
            )
        )

        third = login(client)
        fourth = login(client)
        assert client.post(
            "/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {third['access_token']}"},
        ).status_code == 204
        select_session(client, fourth["refresh_token"], fourth["csrf_token"])
        assert_invalid(
            client.post(
                "/v1/auth/refresh",
                headers={"X-CSRF-Token": fourth["csrf_token"]},
            )
        )

        codec = AccessTokenCodec(AuthSettings())
        expired = codec.issue_access_token(
            registration.json()["id"],
            datetime.now(UTC) - timedelta(minutes=16),
        )
        assert_invalid(
            client.get(
                "/v1/auth/me",
                headers={"Authorization": f"Bearer {expired}"},
            )
        )
        assert_invalid(
            client.get(
                "/v1/auth/me",
                headers={"Authorization": f"Bearer {third['access_token']}x"},
            )
        )

        rate_responses = [
            client.post(
                "/v1/auth/login",
                json={"email": RATE_EMAIL, "password": PASSWORD},
            )
            for _ in range(3)
        ]
        assert all(response.status_code == 401 for response in rate_responses)

        durable = login(client)
        state = {
            "account_id": account_id,
            "email": EMAIL,
            "access_token": durable["access_token"],
            "refresh_token": durable["refresh_token"],
            "csrf_token": durable["csrf_token"],
            "revoked_refresh_token": fourth["refresh_token"],
            "revoked_csrf_token": fourth["csrf_token"],
        }
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        STATE_FILE.chmod(0o600)


def test_verify_persistence_after_postgres_and_redis_restart() -> None:
    require_phase("verify")
    state: dict[str, str] = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        current = client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {state['access_token']}"},
        )
        assert current.status_code == 200
        assert current.json()["id"] == state["account_id"]
        assert current.json()["email"] == state["email"]

        select_session(client, state["refresh_token"], state["csrf_token"])
        refreshed = client.post(
            "/v1/auth/refresh",
            headers={"X-CSRF-Token": state["csrf_token"]},
        )
        assert refreshed.status_code == 200
        active_refresh = client.cookies.get("trialscribe_refresh")
        active_csrf = client.cookies.get("trialscribe_csrf")
        assert active_refresh and active_csrf

        select_session(
            client,
            state["revoked_refresh_token"],
            state["revoked_csrf_token"],
        )
        assert_invalid(
            client.post(
                "/v1/auth/refresh",
                headers={"X-CSRF-Token": state["revoked_csrf_token"]},
            )
        )

        rate_responses = [
            client.post(
                "/v1/auth/login",
                json={"email": RATE_EMAIL, "password": PASSWORD},
            )
            for _ in range(3)
        ]
        assert [response.status_code for response in rate_responses] == [401, 401, 429]

        select_session(client, f"{active_refresh}tampered", active_csrf)
        assert_invalid(
            client.post(
                "/v1/auth/refresh",
                headers={"X-CSRF-Token": active_csrf},
            )
        )

        duplicate = client.post(
            "/v1/auth/register",
            json={"email": EMAIL.upper(), "password": PASSWORD},
        )
        assert duplicate.status_code == 409
