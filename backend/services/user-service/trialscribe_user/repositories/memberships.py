"""SQLAlchemy persistence for organization memberships."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_user.models.membership import Membership, MembershipRole


class DuplicateMembershipError(RuntimeError):
    """An account already belongs to an organization."""


class MembershipRepository:
    """Persist and retrieve memberships in one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> Membership:
        self._session.add(membership)
        try:
            await self._session.flush()
        except IntegrityError:
            raise DuplicateMembershipError("Account already belongs to organization") from None
        return membership

    async def get(
        self,
        organization_id: UUID,
        account_id: UUID,
    ) -> Membership | None:
        result = await self._session.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.account_id == account_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        memberships = await self._session.scalars(
            select(Membership)
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.created_at, Membership.id)
        )
        return list(memberships)

    async def lock_for_organization(self, organization_id: UUID) -> list[Membership]:
        memberships = await self._session.scalars(
            select(Membership)
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.id)
            .with_for_update()
        )
        return list(memberships)

    async def update_role(
        self,
        membership: Membership,
        role: MembershipRole,
    ) -> Membership:
        membership.role = role.value
        await self._session.flush()
        return membership

    async def remove(self, membership: Membership) -> None:
        await self._session.delete(membership)
        await self._session.flush()
