import asyncio
from uuid import UUID

import pytest

from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.services.authorization import (
    AuthorizationService,
    OrganizationAction,
    OrganizationNotFoundError,
    PermissionDeniedError,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000010")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000011")


class FakeMembershipRepository:
    def __init__(self, membership: Membership | None) -> None:
        self.membership = membership
        self.requests: list[tuple[UUID, UUID]] = []

    async def get(self, organization_id: UUID, account_id: UUID) -> Membership | None:
        self.requests.append((organization_id, account_id))
        return self.membership


def membership(role: MembershipRole) -> Membership:
    return Membership(
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        role=role.value,
    )


def test_permission_matrix_is_explicit_and_denies_unknown_roles() -> None:
    assert all(
        AuthorizationService.allows(MembershipRole.OWNER, action)
        for action in OrganizationAction
    )
    assert AuthorizationService.allows(MembershipRole.ADMIN, OrganizationAction.READ)
    assert AuthorizationService.allows(
        MembershipRole.ADMIN,
        OrganizationAction.INVITE_MEMBER,
    )
    assert not AuthorizationService.allows(
        MembershipRole.ADMIN,
        OrganizationAction.INVITE_ADMIN,
    )
    assert AuthorizationService.allows(MembershipRole.MEMBER, OrganizationAction.READ)
    assert not AuthorizationService.allows(
        MembershipRole.MEMBER,
        OrganizationAction.REMOVE_MEMBER,
    )
    assert not AuthorizationService.allows("unknown", OrganizationAction.READ)


def test_require_permission_uses_current_membership() -> None:
    repository = FakeMembershipRepository(membership(MembershipRole.ADMIN))
    service = AuthorizationService(repository)  # type: ignore[arg-type]

    result = asyncio.run(
        service.require_permission(ACCOUNT_ID, ORGANIZATION_ID, OrganizationAction.READ)
    )

    assert result.role == MembershipRole.ADMIN.value
    assert repository.requests == [(ORGANIZATION_ID, ACCOUNT_ID)]


def test_missing_membership_hides_the_organization() -> None:
    service = AuthorizationService(FakeMembershipRepository(None))  # type: ignore[arg-type]

    with pytest.raises(OrganizationNotFoundError, match="Organization not found"):
        asyncio.run(
            service.require_permission(
                ACCOUNT_ID,
                ORGANIZATION_ID,
                OrganizationAction.READ,
            )
        )


def test_insufficient_role_is_denied() -> None:
    service = AuthorizationService(  # type: ignore[arg-type]
        FakeMembershipRepository(membership(MembershipRole.MEMBER))
    )

    with pytest.raises(PermissionDeniedError, match="permission denied"):
        asyncio.run(
            service.require_permission(
                ACCOUNT_ID,
                ORGANIZATION_ID,
                OrganizationAction.INVITE_MEMBER,
            )
        )
