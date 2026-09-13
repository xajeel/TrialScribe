"""SQLAlchemy persistence for refresh-token session families."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_auth.models.session import AuthSession, RefreshToken


class SessionRepository:
    """Persist session state within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_session(
        self,
        auth_session: AuthSession,
        refresh_token: RefreshToken,
    ) -> None:
        self._session.add_all((auth_session, refresh_token))
        await self._session.flush()

    async def load_token_for_update(
        self,
        token_hash: str,
    ) -> tuple[RefreshToken, AuthSession] | None:
        statement = (
            select(RefreshToken, AuthSession)
            .join(AuthSession, RefreshToken.session_id == AuthSession.id)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update(of=(RefreshToken, AuthSession))
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def add_refresh_token(self, refresh_token: RefreshToken) -> None:
        self._session.add(refresh_token)
        await self._session.flush()

    async def flush(self) -> None:
        await self._session.flush()

    async def revoke_all(self, account_id: UUID, revoked_at: datetime) -> int:
        result = await self._session.execute(
            update(AuthSession)
            .where(
                AuthSession.account_id == account_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return result.rowcount or 0
