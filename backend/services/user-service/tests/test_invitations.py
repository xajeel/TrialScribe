import asyncio
import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trialscribe_user.config import UserSettings
from trialscribe_user.models.invitation import Invitation
from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.security.invitations import hash_invitation_token
from trialscribe_user.services.authorization import PermissionDeniedError
from trialscribe_user.services.invitations import (
    InvalidInvitationError,
    InvalidInvitationInput,
    InvitationConflictError,
    InvitationService,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000030")
OWNER_ID = UUID("00000000-0000-4000-8000-000000000031")
ADMIN_ID = UUID("00000000-0000-4000-8000-000000000032")
MEMBER_ID = UUID("00000000-0000-4000-8000-000000000033")
NEW_ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000034")


class FakeMembershipRepository:
    def __init__(self, memberships: list[Membership]) -> None:
        self.memberships = memberships

    async def get(self, organization_id: UUID, account_id: UUID) -> Membership | None:
        return next(
            (
                item
                for item in self.memberships
                if item.organization_id == organization_id and item.account_id == account_id
            ),
            None,
        )

    async def add(self, membership: Membership) -> Membership:
        if await self.get(membership.organization_id, membership.account_id) is not None:
            raise AssertionError("duplicate membership")
        self.memberships.append(membership)
        return membership


class FakeInvitationRepository:
    def __init__(self) -> None:
        self.invitations: list[Invitation] = []
        self.accounts_by_email: dict[str, UUID] = {}
        self.flushes = 0

    async def add(self, invitation: Invitation) -> Invitation:
        self.invitations.append(invitation)
        return invitation

    async def get_pending_for_update(
        self,
        organization_id: UUID,
        normalized_email: str,
    ) -> Invitation | None:
        return next(
            (
                item
                for item in self.invitations
                if item.organization_id == organization_id
                and item.email == normalized_email
                and item.accepted_at is None
                and item.revoked_at is None
            ),
            None,
        )

    async def get_by_hash_for_update(self, token_hash: str) -> Invitation | None:
        return next(
            (item for item in self.invitations if item.token_hash == token_hash),
            None,
        )

    async def find_account_id_by_email(self, normalized_email: str) -> UUID | None:
        return self.accounts_by_email.get(normalized_email)

    async def get_by_id(
        self,
        organization_id: UUID,
        invitation_id: UUID,
    ) -> Invitation | None:
        return next(
            (
                item
                for item in self.invitations
                if item.organization_id == organization_id and item.id == invitation_id
            ),
            None,
        )

    async def list_for_organization(self, organization_id: UUID) -> list[Invitation]:
        return [item for item in self.invitations if item.organization_id == organization_id]

    async def flush(self) -> None:
        self.flushes += 1


def settings() -> UserSettings:
    public_key = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return UserSettings(
        auth_jwt_public_key_b64=base64.b64encode(public_key).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
        user_invitation_ttl_seconds=604800,
        user_invitation_accept_url="https://app.example.com/invitations/accept",
    )


def membership(account_id: UUID, role: MembershipRole) -> Membership:
    return Membership(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        account_id=account_id,
        role=role.value,
    )


def service_with(
    memberships: list[Membership],
) -> tuple[InvitationService, FakeInvitationRepository, FakeMembershipRepository]:
    invitations = FakeInvitationRepository()
    membership_repository = FakeMembershipRepository(memberships)
    service = InvitationService(  # type: ignore[arg-type]
        invitations,
        membership_repository,
        settings(),
    )
    return service, invitations, membership_repository


def create_invite(
    service: InvitationService,
    actor_id: UUID = OWNER_ID,
    role: MembershipRole = MembershipRole.MEMBER,
    now: datetime = NOW,
) -> tuple[Invitation, str, str]:
    invitation, accept_url = asyncio.run(
        service.create_invitation(
            actor_id,
            ORGANIZATION_ID,
            " Invited.Person@Example.COM ",
            role,
            now,
        )
    )
    token = parse_qs(urlsplit(accept_url).query)["token"][0]
    return invitation, accept_url, token


def test_owner_creates_hash_only_normalized_single_use_link() -> None:
    service, invitations, _ = service_with(
        [membership(OWNER_ID, MembershipRole.OWNER)]
    )

    invitation, accept_url, token = create_invite(service)

    assert accept_url.startswith("https://app.example.com/invitations/accept?")
    assert invitation.email == "invited.person@example.com"
    assert invitation.token_hash == hash_invitation_token(token)
    assert token not in invitation.token_hash
    assert invitation.expires_at == NOW + timedelta(days=7)
    assert invitations.invitations == [invitation]


def test_admin_can_invite_members_but_not_admins() -> None:
    service, _, _ = service_with([membership(ADMIN_ID, MembershipRole.ADMIN)])

    create_invite(service, actor_id=ADMIN_ID)
    with pytest.raises(PermissionDeniedError):
        create_invite(
            service,
            actor_id=ADMIN_ID,
            role=MembershipRole.ADMIN,
            now=NOW + timedelta(seconds=1),
        )


@pytest.mark.parametrize("role", [MembershipRole.OWNER, "unknown"])
def test_invalid_invitation_roles_are_rejected(role: str | MembershipRole) -> None:
    service, _, _ = service_with([membership(OWNER_ID, MembershipRole.OWNER)])

    with pytest.raises(InvalidInvitationInput):
        asyncio.run(
            service.create_invitation(
                OWNER_ID,
                ORGANIZATION_ID,
                "person@example.com",
                role,
                NOW,
            )
        )


def test_live_duplicate_conflicts_and_expired_invite_is_reissued() -> None:
    service, invitations, _ = service_with(
        [membership(OWNER_ID, MembershipRole.OWNER)]
    )
    first, _, _ = create_invite(service)

    with pytest.raises(InvitationConflictError, match="live invitation"):
        create_invite(service, now=NOW + timedelta(seconds=1))

    replacement, _, _ = create_invite(service, now=NOW + timedelta(days=8))
    assert first.revoked_at == NOW + timedelta(days=8)
    assert replacement.id != first.id
    assert len(invitations.invitations) == 2


def test_existing_member_is_rejected_before_an_invitation_is_created() -> None:
    service, invitations, _ = service_with(
        [
            membership(OWNER_ID, MembershipRole.OWNER),
            membership(MEMBER_ID, MembershipRole.MEMBER),
        ]
    )
    invitations.accounts_by_email["invited.person@example.com"] = MEMBER_ID

    with pytest.raises(InvitationConflictError, match="already belongs"):
        create_invite(service)

    assert invitations.invitations == []


def test_acceptance_creates_exact_role_and_replay_is_rejected() -> None:
    service, invitations, memberships = service_with(
        [membership(OWNER_ID, MembershipRole.OWNER)]
    )
    invitation, _, token = create_invite(service, role=MembershipRole.ADMIN)
    invitations.accounts_by_email[invitation.email] = NEW_ACCOUNT_ID

    accepted = asyncio.run(service.accept_invitation(token, NEW_ACCOUNT_ID, NOW))

    assert accepted.role == MembershipRole.ADMIN.value
    assert invitation.accepted_at == NOW
    assert accepted in memberships.memberships
    with pytest.raises(InvalidInvitationError, match="Invalid organization invitation"):
        asyncio.run(service.accept_invitation(token, MEMBER_ID, NOW))
    with pytest.raises(InvalidInvitationError, match="Invalid organization invitation"):
        asyncio.run(service.accept_invitation(f"{token}x", MEMBER_ID, NOW))


def test_forwarded_token_cannot_be_accepted_by_another_account() -> None:
    service, invitations, memberships = service_with(
        [membership(OWNER_ID, MembershipRole.OWNER)]
    )
    invitation, _, token = create_invite(service)
    invitations.accounts_by_email[invitation.email] = NEW_ACCOUNT_ID

    with pytest.raises(InvalidInvitationError, match="Invalid organization invitation"):
        asyncio.run(service.accept_invitation(token, MEMBER_ID, NOW))

    assert invitation.accepted_at is None
    assert all(item.account_id != MEMBER_ID for item in memberships.memberships)
    accepted = asyncio.run(service.accept_invitation(token, NEW_ACCOUNT_ID, NOW))
    assert accepted.account_id == NEW_ACCOUNT_ID


def test_expired_and_revoked_invitations_share_safe_rejection() -> None:
    service, _, _ = service_with([membership(OWNER_ID, MembershipRole.OWNER)])
    expired, _, expired_token = create_invite(service)
    with pytest.raises(InvalidInvitationError, match="Invalid organization invitation"):
        asyncio.run(
            service.accept_invitation(
                expired_token,
                NEW_ACCOUNT_ID,
                expired.expires_at,
            )
        )

    revoked, _, revoked_token = create_invite(service, now=NOW + timedelta(days=8))
    asyncio.run(
        service.revoke_invitation(
            OWNER_ID,
            ORGANIZATION_ID,
            revoked.id,
            NOW + timedelta(days=8),
        )
    )
    with pytest.raises(InvalidInvitationError, match="Invalid organization invitation"):
        asyncio.run(
            service.accept_invitation(
                revoked_token,
                NEW_ACCOUNT_ID,
                NOW + timedelta(days=8),
            )
        )


def test_existing_membership_race_never_changes_access() -> None:
    existing = membership(NEW_ACCOUNT_ID, MembershipRole.MEMBER)
    service, invitations, memberships = service_with(
        [membership(OWNER_ID, MembershipRole.OWNER), existing]
    )
    invitation, _, token = create_invite(service)
    invitations.accounts_by_email[invitation.email] = NEW_ACCOUNT_ID

    with pytest.raises(InvitationConflictError, match="already belongs"):
        asyncio.run(service.accept_invitation(token, NEW_ACCOUNT_ID, NOW))

    assert existing.role == MembershipRole.MEMBER.value
    assert len([item for item in memberships.memberships if item.account_id == NEW_ACCOUNT_ID]) == 1
