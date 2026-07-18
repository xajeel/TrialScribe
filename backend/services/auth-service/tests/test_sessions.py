import base64
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.models.session import AuthSession, RefreshToken
from trialscribe_auth.security.csrf import generate_csrf_token, validate_csrf_token
from trialscribe_auth.services.sessions import SessionService, hash_refresh_token


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
    values: dict[str, Any] = {
        "auth_jwt_private_key_b64": base64.b64encode(private_bytes).decode(),
        "auth_jwt_public_key_b64": base64.b64encode(public_bytes).decode(),
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
    return AuthSettings(**values)


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, AuthSession] = {}
        self.tokens: dict[str, RefreshToken] = {}
        self.fail_next_add = False
        self.flush_count = 0

    async def add_session(
        self,
        auth_session: AuthSession,
        refresh_token: RefreshToken,
    ) -> None:
        self.sessions[auth_session.id] = auth_session
        self.tokens[refresh_token.token_hash] = refresh_token

    async def load_token_for_update(
        self,
        token_hash: str,
    ) -> tuple[RefreshToken, AuthSession] | None:
        token = self.tokens.get(token_hash)
        if token is None:
            return None
        return token, self.sessions[token.session_id]

    async def add_refresh_token(self, refresh_token: RefreshToken) -> None:
        if self.fail_next_add:
            raise RuntimeError("simulated persistence failure")
        self.tokens[refresh_token.token_hash] = refresh_token

    async def flush(self) -> None:
        self.flush_count += 1

    async def revoke_all(self, account_id: UUID, revoked_at: datetime) -> int:
        revoked = 0
        for auth_session in self.sessions.values():
            if auth_session.account_id == account_id and auth_session.revoked_at is None:
                auth_session.revoked_at = revoked_at
                revoked += 1
        return revoked


def session_service() -> tuple[SessionService, FakeSessionRepository, AuthSettings]:
    repository = FakeSessionRepository()
    settings = auth_settings()
    return SessionService(repository, settings), repository, settings  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_create_session_persists_only_hash_and_bound_csrf() -> None:
    service, repository, settings = session_service()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)

    credentials = await service.create_session(uuid4(), now)

    stored = repository.tokens[hash_refresh_token(credentials.refresh_token)]
    assert stored.token_hash != credentials.refresh_token
    assert len(base64.urlsafe_b64decode(credentials.refresh_token + "=")) == 32
    assert credentials.expires_at == now + timedelta(days=30)
    assert validate_csrf_token(
        credentials.session_id,
        credentials.csrf_token,
        credentials.csrf_token,
        settings.hmac_key(),
    )


@pytest.mark.anyio
async def test_rotation_consumes_once_without_extending_absolute_expiry() -> None:
    service, repository, _ = session_service()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    original = await service.create_session(uuid4(), now)

    result = await service.rotate_session(
        original.refresh_token,
        original.csrf_token,
        original.csrf_token,
        now + timedelta(minutes=10),
    )

    assert result.accepted is True
    assert result.credentials is not None
    assert result.credentials.refresh_token != original.refresh_token
    assert result.credentials.expires_at == original.expires_at
    consumed = repository.tokens[hash_refresh_token(original.refresh_token)]
    assert consumed.consumed_at == now + timedelta(minutes=10)
    assert consumed.replacement_token_id is not None


@pytest.mark.anyio
async def test_replaying_consumed_token_revokes_the_device_family() -> None:
    service, repository, _ = session_service()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    original = await service.create_session(uuid4(), now)
    await service.rotate_session(
        original.refresh_token,
        original.csrf_token,
        original.csrf_token,
        now + timedelta(minutes=1),
    )

    replay = await service.rotate_session(
        original.refresh_token,
        original.csrf_token,
        original.csrf_token,
        now + timedelta(minutes=2),
    )

    assert replay.accepted is False
    assert replay.replayed is True
    assert repository.sessions[original.session_id].revoked_at == now + timedelta(minutes=2)


@pytest.mark.anyio
async def test_failed_replacement_does_not_consume_current_token() -> None:
    service, repository, _ = session_service()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    original = await service.create_session(uuid4(), now)
    repository.fail_next_add = True

    with pytest.raises(RuntimeError, match="persistence failure"):
        await service.rotate_session(
            original.refresh_token,
            original.csrf_token,
            original.csrf_token,
            now + timedelta(minutes=1),
        )

    token = repository.tokens[hash_refresh_token(original.refresh_token)]
    assert token.consumed_at is None
    assert token.replacement_token_id is None


@pytest.mark.anyio
async def test_expired_unknown_and_bad_csrf_have_same_rejected_shape() -> None:
    service, _, _ = session_service()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    original = await service.create_session(uuid4(), now)

    results = [
        await service.rotate_session(
            "unknown",
            original.csrf_token,
            original.csrf_token,
            now,
        ),
        await service.rotate_session(
            original.refresh_token,
            original.csrf_token,
            "tampered",
            now,
        ),
        await service.rotate_session(
            original.refresh_token,
            original.csrf_token,
            original.csrf_token,
            original.expires_at,
        ),
    ]

    assert all(result.credentials is None for result in results)
    assert all(result.replayed is False for result in results)


@pytest.mark.anyio
async def test_current_logout_is_idempotent_and_does_not_revoke_other_device() -> None:
    service, repository, _ = session_service()
    account_id = uuid4()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    first = await service.create_session(account_id, now)
    second = await service.create_session(account_id, now)

    assert await service.revoke_current(
        first.refresh_token,
        first.csrf_token,
        first.csrf_token,
        now,
    )
    assert await service.revoke_current(
        first.refresh_token,
        first.csrf_token,
        first.csrf_token,
        now + timedelta(seconds=1),
    )
    assert repository.sessions[first.session_id].revoked_at == now
    assert repository.sessions[second.session_id].revoked_at is None


@pytest.mark.anyio
async def test_logout_all_revokes_every_session_for_only_one_account() -> None:
    service, repository, _ = session_service()
    account_id = uuid4()
    other_account_id = uuid4()
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    await service.create_session(account_id, now)
    await service.create_session(account_id, now)
    other = await service.create_session(other_account_id, now)

    assert await service.revoke_all(account_id, now) == 2
    assert repository.sessions[other.session_id].revoked_at is None


def test_csrf_rejects_cross_session_mismatch_and_tampering() -> None:
    key = secrets.token_bytes(32)
    session_id = uuid4()
    token = generate_csrf_token(session_id, key)

    assert validate_csrf_token(session_id, token, token, key)
    assert not validate_csrf_token(uuid4(), token, token, key)
    assert not validate_csrf_token(session_id, token, f"{token}x", key)
    assert not validate_csrf_token(session_id, "malformed", "malformed", key)
