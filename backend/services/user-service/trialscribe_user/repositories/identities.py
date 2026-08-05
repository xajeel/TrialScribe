"""Tenant-scoped persistence and bulk lookup for safe account identities."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_user.models.identity import OrganizationIdentityLink
from trialscribe_user.utils.constant import MAX_IDENTITY_RESOLUTION_SIZE


@dataclass(frozen=True, slots=True)
class OrganizationIdentity:
    """Allow-listed account facts visible inside an associated organization."""

    account_id: UUID
    email: str
    is_active: bool


class IdentityRepository:
    """Associate and resolve account identities without granting access."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def associate(self, organization_id: UUID, account_id: UUID) -> None:
        existing = await self._session.scalar(
            select(OrganizationIdentityLink.id).where(
                OrganizationIdentityLink.organization_id == organization_id,
                OrganizationIdentityLink.account_id == account_id,
            )
        )
        if existing is not None:
            return
        self._session.add(
            OrganizationIdentityLink(
                organization_id=organization_id,
                account_id=account_id,
            )
        )
        await self._session.flush()

    async def resolve(
        self,
        organization_id: UUID,
        account_ids: list[UUID] | tuple[UUID, ...] | set[UUID],
    ) -> dict[UUID, OrganizationIdentity]:
        unique_ids = tuple(dict.fromkeys(account_ids))
        if len(unique_ids) > MAX_IDENTITY_RESOLUTION_SIZE:
            raise ValueError("identity resolution exceeds bounded size")
        if not unique_ids:
            return {}
        statement = text(
            "SELECT links.account_id, accounts.email, accounts.is_active "
            "FROM trialscribe.organization_identity_links AS links "
            "JOIN trialscribe.accounts AS accounts ON accounts.id = links.account_id "
            "WHERE links.organization_id = :organization_id "
            "AND links.account_id IN :account_ids "
            "ORDER BY links.account_id"
        ).bindparams(bindparam("account_ids", expanding=True))
        rows = (
            await self._session.execute(
                statement,
                {
                    "organization_id": organization_id,
                    "account_ids": unique_ids,
                },
            )
        ).mappings()
        return {
            row["account_id"]: OrganizationIdentity(
                account_id=row["account_id"],
                email=row["email"],
                is_active=row["is_active"],
            )
            for row in rows
        }

    async def resolve_many(
        self,
        organization_id: UUID,
        account_ids: list[UUID] | tuple[UUID, ...] | set[UUID],
    ) -> dict[UUID, OrganizationIdentity]:
        """Resolve an internal collection through bounded database batches."""

        unique_ids = tuple(dict.fromkeys(account_ids))
        identities: dict[UUID, OrganizationIdentity] = {}
        for offset in range(0, len(unique_ids), MAX_IDENTITY_RESOLUTION_SIZE):
            identities.update(
                await self.resolve(
                    organization_id,
                    unique_ids[offset : offset + MAX_IDENTITY_RESOLUTION_SIZE],
                )
            )
        return identities
