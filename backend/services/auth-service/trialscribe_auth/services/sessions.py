"""Refresh-session creation, rotation, and revocation use cases."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.models.session import AuthSession, RefreshToken
from trialscribe_auth.repositories.sessions import SessionRepository
from trialscribe_auth.security.csrf import generate_csrf_token, validate_csrf_token


def hash_refresh_token(refresh_token: str) -> str:
    """Return the one-way database representation of a refresh token."""

    return hashlib.sha256(refresh_token.encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("session time must include a timezone")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    session_id: UUID
    account_id: UUID
    refresh_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RotationResult:
    credentials: SessionCredentials | None
    replayed: bool = False

    @property
    def accepted(self) -> bool:
        return self.credentials is not None


class SessionService:
    """Manage independently revocable device session families."""

    def __init__(self, repository: SessionRepository, settings: AuthSettings) -> None:
        self._repository = repository
        self._settings = settings

    def _credentials(
        self,
        auth_session: AuthSession,
        refresh_token: str,
    ) -> SessionCredentials:
        return SessionCredentials(
            session_id=auth_session.id,
            account_id=auth_session.account_id,
            refresh_token=refresh_token,
            csrf_token=generate_csrf_token(
                auth_session.id,
                self._settings.hmac_key(),
            ),
            expires_at=auth_session.expires_at,
        )

    async def create_session(
        self,
        account_id: UUID,
        now: datetime,
    ) -> SessionCredentials:
        created_at = _utc(now)
        expires_at = created_at + timedelta(
            seconds=self._settings.auth_refresh_token_ttl_seconds
        )
        auth_session = AuthSession(
            id=uuid4(),
            account_id=account_id,
            expires_at=expires_at,
            last_refreshed_at=created_at,
            revoked_at=None,
        )
        raw_token = secrets.token_urlsafe(32)
        refresh_token = RefreshToken(
            id=uuid4(),
            session_id=auth_session.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
            consumed_at=None,
            replacement_token_id=None,
        )
        await self._repository.add_session(auth_session, refresh_token)
        return self._credentials(auth_session, raw_token)

    async def rotate_session(
        self,
        refresh_token: str,
        cookie_csrf: str,
        header_csrf: str,
        now: datetime,
    ) -> RotationResult:
        refreshed_at = _utc(now)
        loaded = await self._repository.load_token_for_update(
            hash_refresh_token(refresh_token)
        )
        if loaded is None:
            return RotationResult(credentials=None)
        current_token, auth_session = loaded
        if not validate_csrf_token(
            auth_session.id,
            cookie_csrf,
            header_csrf,
            self._settings.hmac_key(),
        ):
            return RotationResult(credentials=None)
        if (
            auth_session.revoked_at is not None
            or auth_session.expires_at <= refreshed_at
            or current_token.expires_at <= refreshed_at
        ):
            return RotationResult(credentials=None)
        if current_token.consumed_at is not None:
            auth_session.revoked_at = refreshed_at
            await self._repository.flush()
            return RotationResult(credentials=None, replayed=True)

        raw_replacement = secrets.token_urlsafe(32)
        replacement = RefreshToken(
            id=uuid4(),
            session_id=auth_session.id,
            token_hash=hash_refresh_token(raw_replacement),
            expires_at=auth_session.expires_at,
            consumed_at=None,
            replacement_token_id=None,
        )
        await self._repository.add_refresh_token(replacement)
        current_token.consumed_at = refreshed_at
        current_token.replacement_token_id = replacement.id
        auth_session.last_refreshed_at = refreshed_at
        await self._repository.flush()
        return RotationResult(
            credentials=self._credentials(auth_session, raw_replacement)
        )

    async def revoke_current(
        self,
        refresh_token: str,
        cookie_csrf: str,
        header_csrf: str,
        now: datetime,
    ) -> bool:
        revoked_at = _utc(now)
        loaded = await self._repository.load_token_for_update(
            hash_refresh_token(refresh_token)
        )
        if loaded is None:
            return False
        _, auth_session = loaded
        if not validate_csrf_token(
            auth_session.id,
            cookie_csrf,
            header_csrf,
            self._settings.hmac_key(),
        ):
            return False
        if auth_session.revoked_at is None:
            auth_session.revoked_at = revoked_at
            await self._repository.flush()
        return True

    async def revoke_all(self, account_id: UUID, now: datetime) -> int:
        return await self._repository.revoke_all(account_id, _utc(now))
