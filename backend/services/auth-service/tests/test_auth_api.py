import base64
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import trialscribe_auth.api.app as app_module
import trialscribe_auth.api.routes as routes_module
from trialscribe_auth.api.app import app
from trialscribe_auth.api.dependencies import (
    get_database_runtime,
    get_now,
    get_rate_limiter,
    get_settings,
    get_token_codec,
)
from trialscribe_auth.config import AuthSettings
from trialscribe_auth.models.account import Account
from trialscribe_auth.models.session import AuthSession, RefreshToken
from trialscribe_auth.repositories.accounts import DuplicateAccountError
from trialscribe_auth.security.rate_limit import RateLimitDecision
from trialscribe_auth.security.tokens import AccessTokenCodec

NOW = datetime(2026, 7, 18, 11, 0, tzinfo=UTC)
PASSWORD = "a valid research passphrase"


def auth_settings() -> AuthSettings:
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
    return AuthSettings(
        auth_jwt_private_key_b64=base64.b64encode(private_bytes).decode(),
        auth_jwt_public_key_b64=base64.b64encode(public_bytes).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
        auth_access_token_ttl_seconds=900,
        auth_refresh_token_ttl_seconds=2_592_000,
        auth_cookie_secure=False,
        auth_hmac_secret=secrets.token_urlsafe(32),
        auth_login_attempt_limit=5,
        auth_login_window_seconds=300,
        redis_url="redis://:private-password@localhost:6379/0",
    )


@dataclass
class AuthState:
    accounts: dict[UUID, Account] = field(default_factory=dict)
    sessions: dict[UUID, AuthSession] = field(default_factory=dict)
    tokens: dict[str, RefreshToken] = field(default_factory=dict)


class FakeDatabaseRuntime:
    def __init__(self, state: AuthState) -> None:
        self.state = state
        self.disposed = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AuthState]:
        yield self.state

    async def dispose(self) -> None:
        self.disposed = True


class FakeAccountRepository:
    def __init__(self, state: AuthState) -> None:
        self.state = state

    async def get_by_email(self, normalized_email: str) -> Account | None:
        return next(
            (
                account
                for account in self.state.accounts.values()
                if account.email == normalized_email
            ),
            None,
        )

    async def get_by_id(self, account_id: UUID) -> Account | None:
        return self.state.accounts.get(account_id)

    async def add(self, account: Account) -> Account:
        if await self.get_by_email(account.email) is not None:
            raise DuplicateAccountError("constraint details")
        account.id = uuid4()
        account.is_active = True
        account.created_at = NOW
        account.updated_at = NOW
        self.state.accounts[account.id] = account
        return account


class FakeSessionRepository:
    def __init__(self, state: AuthState) -> None:
        self.state = state

    async def add_session(
        self,
        auth_session: AuthSession,
        refresh_token: RefreshToken,
    ) -> None:
        self.state.sessions[auth_session.id] = auth_session
        self.state.tokens[refresh_token.token_hash] = refresh_token

    async def load_token_for_update(
        self,
        token_hash: str,
    ) -> tuple[RefreshToken, AuthSession] | None:
        token = self.state.tokens.get(token_hash)
        if token is None:
            return None
        return token, self.state.sessions[token.session_id]

    async def add_refresh_token(self, refresh_token: RefreshToken) -> None:
        self.state.tokens[refresh_token.token_hash] = refresh_token

    async def flush(self) -> None:
        return None

    async def revoke_all(self, account_id: UUID, revoked_at: datetime) -> int:
        count = 0
        for auth_session in self.state.sessions.values():
            if auth_session.account_id == account_id and auth_session.revoked_at is None:
                auth_session.revoked_at = revoked_at
                count += 1
        return count


class FakeRateLimiter:
    def __init__(self) -> None:
        self.failures: dict[tuple[str, str], int] = {}

    async def record_failure(self, email: str, peer: str) -> RateLimitDecision:
        key = (email, peer)
        self.failures[key] = self.failures.get(key, 0) + 1
        if self.failures[key] <= 5:
            return RateLimitDecision(allowed=True)
        return RateLimitDecision(allowed=False, retry_after=300)

    async def clear_success(self, email: str, peer: str) -> None:
        self.failures.pop((email, peer), None)


@pytest.fixture
def api_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    state = AuthState()
    settings = auth_settings()
    database = FakeDatabaseRuntime(state)
    limiter = FakeRateLimiter()
    codec = AccessTokenCodec(settings)
    monkeypatch.setattr(routes_module, "AccountRepository", FakeAccountRepository)
    monkeypatch.setattr(routes_module, "SessionRepository", FakeSessionRepository)
    app.dependency_overrides[get_database_runtime] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_token_codec] = lambda: codec
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        yield {
            "client": TestClient(app),
            "state": state,
            "settings": settings,
            "codec": codec,
            "limiter": limiter,
        }
    finally:
        app.dependency_overrides.clear()


def register_and_login(client: TestClient, email: str = "person@example.com") -> dict[str, Any]:
    registration = client.post(
        "/v1/auth/register",
        json={"email": email, "password": PASSWORD},
    )
    assert registration.status_code == 201
    login = client.post(
        "/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert login.status_code == 200
    return login.json()


def test_register_login_me_and_refresh_contract(api_context: dict[str, Any]) -> None:
    client: TestClient = api_context["client"]
    login = register_and_login(client, "Person@Example.COM")
    original_refresh = client.cookies.get("trialscribe_refresh")
    csrf = client.cookies.get("trialscribe_csrf")

    assert login["token_type"] == "bearer"
    assert login["expires_in"] == 900
    assert "refresh_token" not in login
    assert original_refresh is not None
    assert csrf is not None
    cookie_response = client.post(
        "/v1/auth/login",
        json={"email": "person@example.com", "password": PASSWORD},
    )
    set_cookie = cookie_response.headers.get_list("set-cookie")
    assert any("HttpOnly" in value and "SameSite=strict" in value for value in set_cookie)
    original_refresh = client.cookies.get("trialscribe_refresh")
    csrf = client.cookies.get("trialscribe_csrf")
    assert original_refresh is not None
    assert csrf is not None

    me = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "person@example.com"

    refreshed = client.post("/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    assert client.cookies.get("trialscribe_refresh") != original_refresh
    assert refreshed.json()["expires_in"] == 900


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("unknown@example.com", PASSWORD),
        ("person@example.com", "wrong password value"),
    ],
)
def test_invalid_credentials_share_one_response(
    api_context: dict[str, Any],
    email: str,
    password: str,
) -> None:
    client: TestClient = api_context["client"]
    if email == "person@example.com":
        client.post(
            "/v1/auth/register",
            json={"email": email, "password": PASSWORD},
        )

    response = client.post("/v1/auth/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}


def test_sixth_failed_login_is_throttled(api_context: dict[str, Any]) -> None:
    client: TestClient = api_context["client"]

    responses = [
        client.post(
            "/v1/auth/login",
            json={"email": "unknown@example.com", "password": PASSWORD},
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses] == [401] * 5 + [429]
    assert responses[-1].headers["retry-after"] == "300"


def test_refresh_replay_revokes_replacement_family(api_context: dict[str, Any]) -> None:
    client: TestClient = api_context["client"]
    register_and_login(client)
    original_refresh = client.cookies.get("trialscribe_refresh")
    original_csrf = client.cookies.get("trialscribe_csrf")
    assert original_refresh and original_csrf
    assert client.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": original_csrf},
    ).status_code == 200
    replacement_refresh = client.cookies.get("trialscribe_refresh")
    replacement_csrf = client.cookies.get("trialscribe_csrf")
    assert replacement_refresh and replacement_csrf

    replay = client.post(
        "/v1/auth/refresh",
        headers={
            "Cookie": (
                f"trialscribe_refresh={original_refresh}; "
                f"trialscribe_csrf={original_csrf}"
            ),
            "X-CSRF-Token": original_csrf,
        },
    )
    assert replay.status_code == 401
    assert any("Max-Age=0" in value for value in replay.headers.get_list("set-cookie"))

    revoked_replacement = client.post(
        "/v1/auth/refresh",
        headers={
            "Cookie": (
                f"trialscribe_refresh={replacement_refresh}; "
                f"trialscribe_csrf={replacement_csrf}"
            ),
            "X-CSRF-Token": replacement_csrf,
        },
    )
    assert revoked_replacement.status_code == 401


def test_current_logout_and_logout_all_have_distinct_scope(
    api_context: dict[str, Any],
) -> None:
    first = api_context["client"]
    second = TestClient(app)
    login = register_and_login(first)
    second_login = second.post(
        "/v1/auth/login",
        json={"email": "person@example.com", "password": PASSWORD},
    )
    assert second_login.status_code == 200

    first_csrf = first.cookies.get("trialscribe_csrf")
    assert first_csrf
    logout = first.post("/v1/auth/logout", headers={"X-CSRF-Token": first_csrf})
    assert logout.status_code == 204
    second_csrf = second.cookies.get("trialscribe_csrf")
    assert second_csrf
    assert second.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": second_csrf},
    ).status_code == 200

    logout_all = first.post(
        "/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert logout_all.status_code == 204
    second_csrf = second.cookies.get("trialscribe_csrf")
    assert second_csrf
    assert second.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": second_csrf},
    ).status_code == 401


def test_tampered_and_expired_access_tokens_share_one_response(
    api_context: dict[str, Any],
) -> None:
    client: TestClient = api_context["client"]
    codec: AccessTokenCodec = api_context["codec"]
    login = register_and_login(client)
    account_id = next(iter(api_context["state"].accounts))
    expired = codec.issue_access_token(account_id, NOW - timedelta(minutes=16))
    tampered = f"{login['access_token']}x"

    responses = [
        client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        for token in (expired, tampered)
    ]

    assert all(response.status_code == 401 for response in responses)
    assert all(
        response.json() == {"detail": "Invalid authentication credentials"}
        for response in responses
    )


def test_missing_csrf_rejects_and_clears_session_cookies(
    api_context: dict[str, Any],
) -> None:
    client: TestClient = api_context["client"]
    register_and_login(client)

    response = client.post("/v1/auth/refresh")

    assert response.status_code == 401
    assert len(response.headers.get_list("set-cookie")) == 2
    assert all("Max-Age=0" in value for value in response.headers.get_list("set-cookie"))


class LifecycleRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True

    async def ping(self) -> bool:
        return True


def test_lifespan_closes_database_and_redis_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = auth_settings()
    database = FakeDatabaseRuntime(AuthState())
    redis = LifecycleRedis()
    monkeypatch.setattr(app_module, "AuthSettings", lambda: settings)
    monkeypatch.setattr(app_module, "DatabaseSettings", lambda: object())
    monkeypatch.setattr(app_module, "create_database_runtime", lambda _settings: database)
    monkeypatch.setattr(
        app_module.Redis,
        "from_url",
        lambda _url: redis,
    )

    with TestClient(app):
        assert app.state.database_runtime is database
        assert app.state.redis is redis

    assert database.disposed is True
    assert redis.closed is True
