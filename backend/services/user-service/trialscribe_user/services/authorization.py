"""Deny-by-default organization permission checks."""

from enum import StrEnum
from uuid import UUID

from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.repositories.memberships import MembershipRepository


class OrganizationAction(StrEnum):
    READ = "read"
    INVITE_MEMBER = "invite_member"
    INVITE_ADMIN = "invite_admin"
    REVOKE_MEMBER_INVITATION = "revoke_member_invitation"
    REVOKE_ADMIN_INVITATION = "revoke_admin_invitation"
    REMOVE_MEMBER = "remove_member"
    REMOVE_PRIVILEGED = "remove_privileged"
    CHANGE_ROLES = "change_roles"


PERMISSIONS: dict[MembershipRole, frozenset[OrganizationAction]] = {
    MembershipRole.OWNER: frozenset(OrganizationAction),
    MembershipRole.ADMIN: frozenset(
        {
            OrganizationAction.READ,
            OrganizationAction.INVITE_MEMBER,
            OrganizationAction.REVOKE_MEMBER_INVITATION,
            OrganizationAction.REMOVE_MEMBER,
        }
    ),
    MembershipRole.MEMBER: frozenset({OrganizationAction.READ}),
}


class OrganizationNotFoundError(LookupError):
    """The organization is not visible to the current account."""


class PermissionDeniedError(PermissionError):
    """The current organization role does not allow an action."""


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
        return action in PERMISSIONS.get(normalized_role, frozenset())

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
