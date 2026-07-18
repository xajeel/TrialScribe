"""SQLAlchemy persistence for authentication accounts."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_auth.models.account import Account


class DuplicateAccountError(RuntimeError):
    """A normalized email already belongs to an account."""


class AccountRepository:
    """Persist and retrieve accounts within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, normalized_email: str) -> Account | None:
        result = await self._session.execute(
            select(Account).where(Account.email == normalized_email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, account_id: UUID) -> Account | None:
        return await self._session.get(Account, account_id)

    async def add(self, account: Account) -> Account:
        self._session.add(account)
        try:
            await self._session.flush()
        except IntegrityError:
            raise DuplicateAccountError("Account could not be created") from None
        return account
