import asyncio
from uuid import UUID, uuid4

import pytest

from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.models.organization import Organization
from trialscribe_user.services.authorization import PermissionDeniedError
from trialscribe_user.services.organizations import (
    InvalidOrganizationInput,
    MembershipConflictError,
    OrganizationService,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000020")
OWNER_ID = UUID("00000000-0000-4000-8000-000000000021")
SECOND_OWNER_ID = UUID("00000000-0000-4000-8000-000000000022")
ADMIN_ID = UUID("00000000-0000-4000-8000-000000000023")
MEMBER_ID = UUID("00000000-0000-4000-8000-000000000024")


class FakeOrganizationRepository:
    def __init__(self) -> None:
        self.organizations: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> Organization:
        organization.id = ORGANIZATION_ID
        self.organizations[organization.id] = organization
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self.organizations.get(organization_id)

    async def list_for_account(
        self,
        _account_id: UUID,
    ) -> list[tuple[Organization, Membership]]:
        return []


class FakeMembershipRepository:
    def __init__(self, memberships: list[Membership] | None = None) -> None:
        self.memberships = memberships or []
        self.lock_count = 0

    async def add(self, membership: Membership) -> Membership:
        membership.id = uuid4()
        self.memberships.append(membership)
        return membership

    async def get(self, organization_id: UUID, account_id: UUID) -> Membership | None:
        return next(
            (
                item
                for item in self.memberships
                if item.organization_id == organization_id and item.account_id == account_id
            ),
            None,
        )

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        return [item for item in self.memberships if item.organization_id == organization_id]

    async def lock_for_organization(self, organization_id: UUID) -> list[Membership]:
        self.lock_count += 1
        return await self.list_for_organization(organization_id)

    async def update_role(
        self,
        membership: Membership,
        role: MembershipRole,
    ) -> Membership:
        membership.role = role.value
        return membership

    async def remove(self, membership: Membership) -> None:
        self.memberships.remove(membership)


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.associations: set[tuple[UUID, UUID]] = set()

    async def associate(self, organization_id: UUID, account_id: UUID) -> None:
        self.associations.add((organization_id, account_id))


def make_membership(account_id: UUID, role: MembershipRole) -> Membership:
    return Membership(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        account_id=account_id,
        role=role.value,
    )


def service_with(
    memberships: list[Membership] | None = None,
) -> tuple[
    OrganizationService,
    FakeOrganizationRepository,
    FakeMembershipRepository,
    FakeIdentityRepository,
]:
    organizations = FakeOrganizationRepository()
    membership_repository = FakeMembershipRepository(memberships)
    identity_repository = FakeIdentityRepository()
    service = OrganizationService(  # type: ignore[arg-type]
        organizations,
        membership_repository,
        identity_repository,
    )
    return service, organizations, membership_repository, identity_repository


def test_create_organization_trims_name_and_assigns_owner_atomically() -> None:
    service, organizations, memberships, identities = service_with()

    organization, membership = asyncio.run(
        service.create_organization(OWNER_ID, "  Research Team  ")
    )

    assert organization.name == "Research Team"
    assert organizations.organizations[ORGANIZATION_ID] is organization
    assert membership.organization_id == organization.id
    assert membership.account_id == OWNER_ID
    assert membership.role == MembershipRole.OWNER.value
    assert memberships.memberships == [membership]
    assert identities.associations == {(ORGANIZATION_ID, OWNER_ID)}


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_invalid_organization_names_are_rejected(name: str) -> None:
    service, _, _, _ = service_with()

    with pytest.raises(InvalidOrganizationInput):
        asyncio.run(service.create_organization(OWNER_ID, name))


def test_owner_can_promote_member_when_rows_are_locked() -> None:
    service, _, repository, _ = service_with(
        [
            make_membership(OWNER_ID, MembershipRole.OWNER),
            make_membership(MEMBER_ID, MembershipRole.MEMBER),
        ]
    )

    changed = asyncio.run(
        service.change_role(OWNER_ID, ORGANIZATION_ID, MEMBER_ID, MembershipRole.ADMIN)
    )

    assert changed.role == MembershipRole.ADMIN.value
    assert repository.lock_count == 1


def test_last_owner_cannot_remove_or_demote_self() -> None:
    service, _, repository, _ = service_with(
        [make_membership(OWNER_ID, MembershipRole.OWNER)]
    )

    with pytest.raises(MembershipConflictError, match="retain at least one owner"):
        asyncio.run(
            service.change_role(
                OWNER_ID,
                ORGANIZATION_ID,
                OWNER_ID,
                MembershipRole.ADMIN,
            )
        )
    with pytest.raises(MembershipConflictError, match="retain at least one owner"):
        asyncio.run(service.remove_member(OWNER_ID, ORGANIZATION_ID, OWNER_ID))

    assert repository.memberships[0].role == MembershipRole.OWNER.value


def test_owner_handoff_is_allowed_when_another_owner_remains() -> None:
    service, _, repository, _ = service_with(
        [
            make_membership(OWNER_ID, MembershipRole.OWNER),
            make_membership(SECOND_OWNER_ID, MembershipRole.OWNER),
        ]
    )

    asyncio.run(service.remove_member(OWNER_ID, ORGANIZATION_ID, OWNER_ID))

    assert [item.account_id for item in repository.memberships] == [SECOND_OWNER_ID]


def test_admin_can_remove_members_but_not_admins_or_owners() -> None:
    service, _, repository, identities = service_with(
        [
            make_membership(OWNER_ID, MembershipRole.OWNER),
            make_membership(ADMIN_ID, MembershipRole.ADMIN),
            make_membership(MEMBER_ID, MembershipRole.MEMBER),
        ]
    )

    asyncio.run(service.remove_member(ADMIN_ID, ORGANIZATION_ID, MEMBER_ID))
    assert MEMBER_ID not in {item.account_id for item in repository.memberships}
    assert identities.associations == set()

    with pytest.raises(PermissionDeniedError):
        asyncio.run(service.remove_member(ADMIN_ID, ORGANIZATION_ID, OWNER_ID))
