"""Authorized organization identity-directory use cases."""

from uuid import UUID

from trialscribe_user.repositories.identities import (
    IdentityRepository,
    OrganizationIdentity,
)
from trialscribe_user.repositories.memberships import MembershipRepository
from trialscribe_user.services.authorization import (
    AuthorizationService,
    OrganizationAction,
)


class IdentityDirectoryService:
    """Resolve only identities linked to an organization the actor can read."""

    def __init__(
        self,
        memberships: MembershipRepository,
        identities: IdentityRepository,
    ) -> None:
        self._authorization = AuthorizationService(memberships)
        self._identities = identities

    async def resolve(
        self,
        actor_account_id: UUID,
        organization_id: UUID,
        account_ids: list[UUID],
    ) -> dict[UUID, OrganizationIdentity]:
        await self._authorization.require_permission(
            actor_account_id,
            organization_id,
            OrganizationAction.READ,
        )
        return await self._identities.resolve(organization_id, account_ids)
