"""Deny-by-default organization permission checks."""

from uuid import UUID

from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.repositories.memberships import MembershipRepository
from trialscribe_user.utils.constant import ORGANIZATION_PERMISSIONS
from trialscribe_user.utils.enum import OrganizationAction
from trialscribe_user.utils.exceptions import (
    OrganizationNotFoundError,
    PermissionDeniedError,
)


class AuthorizationService:
    """Authorize actions from current persisted memberships."""

    def __init__(self, repository: MembershipRepository) -> None:
        self._repository = repository

    @staticmethod
    def allows(role: str | MembershipRole, action: OrganizationAction) -> bool:
        try:
            normalized_role = MembershipRole(role)
        except ValueError:
            return False
        return action in ORGANIZATION_PERMISSIONS.get(normalized_role, frozenset())

    async def require_permission(
        self,
        account_id: UUID,
        organization_id: UUID,
        action: OrganizationAction,
    ) -> Membership:
        membership = await self._repository.get(organization_id, account_id)
        if membership is None:
            raise OrganizationNotFoundError("Organization not found")
        if not self.allows(membership.role, action):
            raise PermissionDeniedError("Organization permission denied")
        return membership
