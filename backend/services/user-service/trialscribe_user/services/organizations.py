"""Organization creation and membership-management use cases."""

from uuid import UUID

from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.models.organization import Organization
from trialscribe_user.repositories.identities import IdentityRepository
from trialscribe_user.repositories.memberships import MembershipRepository
from trialscribe_user.repositories.organizations import OrganizationRepository
from trialscribe_user.services.authorization import (
    AuthorizationService,
    OrganizationAction,
    OrganizationNotFoundError,
    PermissionDeniedError,
)
from trialscribe_user.utils.exceptions import (
    InvalidOrganizationInput,
    MembershipConflictError,
)


class OrganizationService:
    """Manage organizations through injected transaction repositories."""

    def __init__(
        self,
        organizations: OrganizationRepository,
        memberships: MembershipRepository,
        identities: IdentityRepository | None = None,
    ) -> None:
        self._organizations = organizations
        self._memberships = memberships
        self._identities = identities
        self._authorization = AuthorizationService(memberships)

    async def create_organization(
        self,
        account_id: UUID,
        name: str,
    ) -> tuple[Organization, Membership]:
        normalized_name = name.strip()
        if not 1 <= len(normalized_name) <= 120:
            raise InvalidOrganizationInput(
                "Organization name must be 1 to 120 characters"
            )
        organization = await self._organizations.add(Organization(name=normalized_name))
        membership = await self._memberships.add(
            Membership(
                organization_id=organization.id,
                account_id=account_id,
                role=MembershipRole.OWNER.value,
            )
        )
        if self._identities is not None:
            await self._identities.associate(organization.id, account_id)
        return organization, membership

    async def list_organizations(
        self,
        account_id: UUID,
    ) -> list[tuple[Organization, Membership]]:
        return await self._organizations.list_for_account(account_id)

    async def get_organization(
        self,
        account_id: UUID,
        organization_id: UUID,
    ) -> tuple[Organization, Membership]:
        membership = await self._authorization.require_permission(
            account_id,
            organization_id,
            OrganizationAction.READ,
        )
        organization = await self._organizations.get_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundError("Organization not found")
        return organization, membership

    async def list_members(
        self,
        account_id: UUID,
        organization_id: UUID,
    ) -> list[Membership]:
        await self._authorization.require_permission(
            account_id,
            organization_id,
            OrganizationAction.READ,
        )
        return await self._memberships.list_for_organization(organization_id)

    async def change_role(
        self,
        actor_account_id: UUID,
        organization_id: UUID,
        target_account_id: UUID,
        role: str | MembershipRole,
    ) -> Membership:
        try:
            new_role = MembershipRole(role)
        except ValueError:
            raise InvalidOrganizationInput("Organization role is invalid") from None
        memberships = await self._memberships.lock_for_organization(organization_id)
        actor = self._find_membership(memberships, actor_account_id)
        target = self._find_membership(memberships, target_account_id)
        if actor is None or target is None:
            raise OrganizationNotFoundError("Organization membership not found")
        if not self._authorization.allows(actor.role, OrganizationAction.CHANGE_ROLES):
            raise PermissionDeniedError("Organization permission denied")
        if (
            target.role == MembershipRole.OWNER.value
            and new_role is not MembershipRole.OWNER
        ):
            self._require_another_owner(memberships, target.account_id)
        return await self._memberships.update_role(target, new_role)

    async def remove_member(
        self,
        actor_account_id: UUID,
        organization_id: UUID,
        target_account_id: UUID,
    ) -> None:
        memberships = await self._memberships.lock_for_organization(organization_id)
        actor = self._find_membership(memberships, actor_account_id)
        target = self._find_membership(memberships, target_account_id)
        if actor is None or target is None:
            raise OrganizationNotFoundError("Organization membership not found")
        action = (
            OrganizationAction.REMOVE_MEMBER
            if target.role == MembershipRole.MEMBER.value
            else OrganizationAction.REMOVE_PRIVILEGED
        )
        if not self._authorization.allows(actor.role, action):
            raise PermissionDeniedError("Organization permission denied")
        if target.role == MembershipRole.OWNER.value:
            self._require_another_owner(memberships, target.account_id)
        await self._memberships.remove(target)

    @staticmethod
    def _find_membership(
        memberships: list[Membership],
        account_id: UUID,
    ) -> Membership | None:
        return next(
            (
                membership
                for membership in memberships
                if membership.account_id == account_id
            ),
            None,
        )

    @staticmethod
    def _require_another_owner(
        memberships: list[Membership],
        excluded_account_id: UUID,
    ) -> None:
        if not any(
            membership.role == MembershipRole.OWNER.value
            and membership.account_id != excluded_account_id
            for membership in memberships
        ):
            raise MembershipConflictError("Organization must retain at least one owner")
