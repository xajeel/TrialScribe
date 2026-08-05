"""Organization invitation creation, revocation, and acceptance use cases."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from email_validator import EmailNotValidError, validate_email

from trialscribe_user.config import UserSettings
from trialscribe_user.models.invitation import Invitation
from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.repositories.identities import IdentityRepository
from trialscribe_user.repositories.invitations import (
    DuplicateInvitationError,
    InvitationRepository,
)
from trialscribe_user.repositories.memberships import (
    DuplicateMembershipError,
    MembershipRepository,
)
from trialscribe_user.security.invitations import (
    build_invitation_url,
    generate_invitation_token,
    hash_invitation_token,
)
from trialscribe_user.services.authorization import (
    AuthorizationService,
    OrganizationAction,
)
from trialscribe_user.utils.exceptions import (
    InvalidInvitationError,
    InvalidInvitationInput,
    InvitationConflictError,
)


def normalize_email(email: str) -> str:
    """Match authentication's comparison-safe email representation."""

    try:
        result = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError:
        raise InvalidInvitationInput("Email address is invalid") from None
    return result.normalized.casefold()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invitation time must include a timezone")
    return value.astimezone(UTC)


class InvitationService:
    """Manage single-use organization invitations."""

    def __init__(
        self,
        invitations: InvitationRepository,
        memberships: MembershipRepository,
        settings: UserSettings,
        identities: IdentityRepository | None = None,
    ) -> None:
        self._invitations = invitations
        self._memberships = memberships
        self._identities = identities
        self._authorization = AuthorizationService(memberships)
        self._settings = settings

    async def create_invitation(
        self,
        actor_account_id: UUID,
        organization_id: UUID,
        email: str,
        role: str | MembershipRole,
        now: datetime,
    ) -> tuple[Invitation, str]:
        created_at = _utc(now)
        normalized_email = normalize_email(email)
        invited_role = self._invitation_role(role)
        action = (
            OrganizationAction.INVITE_ADMIN
            if invited_role is MembershipRole.ADMIN
            else OrganizationAction.INVITE_MEMBER
        )
        await self._authorization.require_permission(
            actor_account_id,
            organization_id,
            action,
        )
        if await self._account_is_member(organization_id, normalized_email):
            raise InvitationConflictError("Account already belongs to organization")

        pending = await self._invitations.get_pending_for_update(
            organization_id,
            normalized_email,
        )
        if pending is not None:
            if pending.expires_at > created_at:
                raise InvitationConflictError("A live invitation already exists")
            pending.revoked_at = created_at
            await self._invitations.flush()

        raw_token = generate_invitation_token()
        invitation = Invitation(
            id=uuid4(),
            organization_id=organization_id,
            email=normalized_email,
            role=invited_role.value,
            invited_by_account_id=actor_account_id,
            token_hash=hash_invitation_token(raw_token),
            expires_at=created_at
            + timedelta(seconds=self._settings.user_invitation_ttl_seconds),
            accepted_at=None,
            revoked_at=None,
        )
        try:
            await self._invitations.add(invitation)
        except DuplicateInvitationError:
            raise InvitationConflictError("Invitation could not be created") from None
        return invitation, build_invitation_url(
            self._settings.invitation_accept_url(),
            raw_token,
        )

    async def list_invitations(
        self,
        actor_account_id: UUID,
        organization_id: UUID,
    ) -> list[Invitation]:
        await self._authorization.require_permission(
            actor_account_id,
            organization_id,
            OrganizationAction.REVOKE_MEMBER_INVITATION,
        )
        invitations = await self._invitations.list_for_organization(organization_id)
        actor = await self._memberships.get(organization_id, actor_account_id)
        if actor is not None and actor.role == MembershipRole.ADMIN.value:
            return [
                item for item in invitations if item.role == MembershipRole.MEMBER.value
            ]
        return invitations

    async def revoke_invitation(
        self,
        actor_account_id: UUID,
        organization_id: UUID,
        invitation_id: UUID,
        now: datetime,
    ) -> Invitation:
        invitation = await self._invitations.get_by_id(organization_id, invitation_id)
        if invitation is None or invitation.accepted_at is not None:
            raise InvalidInvitationError("Invalid organization invitation")
        action = (
            OrganizationAction.REVOKE_ADMIN_INVITATION
            if invitation.role == MembershipRole.ADMIN.value
            else OrganizationAction.REVOKE_MEMBER_INVITATION
        )
        await self._authorization.require_permission(
            actor_account_id,
            organization_id,
            action,
        )
        if invitation.revoked_at is None:
            invitation.revoked_at = _utc(now)
            await self._invitations.flush()
        return invitation

    async def accept_invitation(
        self,
        token: str,
        account_id: UUID,
        now: datetime,
    ) -> Membership:
        accepted_at = _utc(now)
        invitation = await self._invitations.get_by_hash_for_update(
            hash_invitation_token(token)
        )
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or invitation.expires_at <= accepted_at
        ):
            raise InvalidInvitationError("Invalid organization invitation")
        invited_account_id = await self._invitations.find_account_id_by_email(
            invitation.email
        )
        if invited_account_id != account_id:
            raise InvalidInvitationError("Invalid organization invitation")
        if (
            await self._memberships.get(invitation.organization_id, account_id)
            is not None
        ):
            raise InvitationConflictError("Account already belongs to organization")
        membership = Membership(
            id=uuid4(),
            organization_id=invitation.organization_id,
            account_id=account_id,
            role=invitation.role,
        )
        try:
            await self._memberships.add(membership)
        except DuplicateMembershipError:
            raise InvitationConflictError(
                "Account already belongs to organization"
            ) from None
        if self._identities is not None:
            await self._identities.associate(invitation.organization_id, account_id)
        invitation.accepted_at = accepted_at
        await self._invitations.flush()
        return membership

    async def _account_is_member(
        self,
        organization_id: UUID,
        normalized_email: str,
    ) -> bool:
        account_id = await self._invitations.find_account_id_by_email(normalized_email)
        if account_id is None:
            return False
        return await self._memberships.get(organization_id, account_id) is not None

    @staticmethod
    def _invitation_role(role: str | MembershipRole) -> MembershipRole:
        try:
            normalized_role = MembershipRole(role)
        except ValueError:
            raise InvalidInvitationInput(
                "Invitation role must be admin or member"
            ) from None
        if normalized_role not in {MembershipRole.ADMIN, MembershipRole.MEMBER}:
            raise InvalidInvitationInput("Invitation role must be admin or member")
        return normalized_role
