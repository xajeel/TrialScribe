"""SQLAlchemy persistence for organization invitations."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_user.models.invitation import Invitation
from trialscribe_user.utils.exceptions import DuplicateInvitationError


class InvitationRepository:
    """Persist invitation state within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invitation: Invitation) -> Invitation:
        self._session.add(invitation)
        try:
            await self._session.flush()
        except IntegrityError:
            raise DuplicateInvitationError("Invitation could not be created") from None
        return invitation

    async def get_pending_for_update(
        self,
        organization_id: UUID,
        normalized_email: str,
    ) -> Invitation | None:
        result = await self._session.execute(
            select(Invitation)
            .where(
                Invitation.organization_id == organization_id,
                Invitation.email == normalized_email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_hash_for_update(self, token_hash: str) -> Invitation | None:
        result = await self._session.execute(
            select(Invitation)
            .where(Invitation.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_account_id_by_email(self, normalized_email: str) -> UUID | None:
        """Resolve an authentication-owned account without importing that service."""

        result = await self._session.execute(
            text("SELECT id FROM trialscribe.accounts WHERE email = :email"),
            {"email": normalized_email},
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        organization_id: UUID,
        invitation_id: UUID,
    ) -> Invitation | None:
        result = await self._session.execute(
            select(Invitation).where(
                Invitation.organization_id == organization_id,
                Invitation.id == invitation_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: UUID) -> list[Invitation]:
        invitations = await self._session.scalars(
            select(Invitation)
            .where(Invitation.organization_id == organization_id)
            .order_by(Invitation.created_at, Invitation.id)
        )
        return list(invitations)

    async def flush(self) -> None:
        await self._session.flush()
