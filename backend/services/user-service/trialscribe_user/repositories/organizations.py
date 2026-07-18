"""SQLAlchemy persistence for organizations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_user.models.membership import Membership
from trialscribe_user.models.organization import Organization


class OrganizationRepository:
    """Persist and retrieve organizations within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> Organization:
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def list_for_account(
        self,
        account_id: UUID,
    ) -> list[tuple[Organization, Membership]]:
        result = await self._session.execute(
            select(Organization, Membership)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.account_id == account_id)
            .order_by(Organization.name, Organization.id)
        )
        return list(result.tuples())
