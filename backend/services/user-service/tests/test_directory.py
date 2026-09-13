import asyncio
from uuid import UUID, uuid4

import pytest

from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.repositories.identities import OrganizationIdentity
from trialscribe_user.services.authorization import OrganizationNotFoundError
from trialscribe_user.services.directory import IdentityDirectoryService

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000091")
FOREIGN_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000092")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000093")
MEMBER_ID = UUID("00000000-0000-4000-8000-000000000094")


class FakeMembershipRepository:
    async def get(self, organization_id: UUID, account_id: UUID) -> Membership | None:
        if organization_id != ORGANIZATION_ID or account_id != ACTOR_ID:
            return None
        return Membership(
            id=uuid4(),
            organization_id=organization_id,
            account_id=account_id,
            role=MembershipRole.MEMBER.value,
        )


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, list[UUID]]] = []

    async def resolve(
        self,
        organization_id: UUID,
        account_ids: list[UUID],
    ) -> dict[UUID, OrganizationIdentity]:
        self.calls.append((organization_id, account_ids))
        return {
            MEMBER_ID: OrganizationIdentity(
                account_id=MEMBER_ID,
                email="member@example.com",
                is_active=True,
            )
        }


def test_current_member_resolves_only_repository_allow_list() -> None:
    identities = FakeIdentityRepository()
    unknown_id = uuid4()
    service = IdentityDirectoryService(  # type: ignore[arg-type]
        FakeMembershipRepository(),
        identities,
    )

    result = asyncio.run(
        service.resolve(ACTOR_ID, ORGANIZATION_ID, [MEMBER_ID, unknown_id])
    )

    assert list(result) == [MEMBER_ID]
    assert identities.calls == [(ORGANIZATION_ID, [MEMBER_ID, unknown_id])]


def test_foreign_organization_is_denied_before_identity_lookup() -> None:
    identities = FakeIdentityRepository()
    service = IdentityDirectoryService(  # type: ignore[arg-type]
        FakeMembershipRepository(),
        identities,
    )

    with pytest.raises(OrganizationNotFoundError):
        asyncio.run(service.resolve(ACTOR_ID, FOREIGN_ORGANIZATION_ID, [MEMBER_ID]))

    assert identities.calls == []
