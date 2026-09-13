"""SQLAlchemy persistence for conversation access grants."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.conversation_access import ConversationAccess


class ConversationAccessRepository:
    """Persist access grants within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        account_id: UUID,
    ) -> ConversationAccess:
        access = ConversationAccess(
            conversation_id=conversation_id,
            organization_id=organization_id,
            account_id=account_id,
        )
        self._session.add(access)
        await self._session.flush()
        return access

    async def list_collaborator_ids(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        owner_account_id: UUID,
    ) -> list[UUID]:
        return list(
            await self._session.scalars(
                select(ConversationAccess.account_id)
                .where(
                    ConversationAccess.conversation_id == conversation_id,
                    ConversationAccess.organization_id == organization_id,
                    ConversationAccess.account_id != owner_account_id,
                )
                .order_by(ConversationAccess.account_id)
            )
        )

    async def list_collaborators_for(
        self,
        conversation_ids: Sequence[UUID],
        organization_id: UUID,
        owner_by_conversation: Mapping[UUID, UUID],
    ) -> dict[UUID, list[UUID]]:
        """Load collaborators for a page of conversations in one statement.

        Asking per conversation turns one listing into one query per row, so a
        page of fifty conversations became fifty-one round trips. One `IN` over
        the page returns the same grants, and each conversation's own owner is
        dropped exactly as the single-conversation read does.
        """

        grouped: dict[UUID, list[UUID]] = {
            conversation_id: [] for conversation_id in conversation_ids
        }
        if not conversation_ids:
            return grouped
        rows = await self._session.execute(
            select(
                ConversationAccess.conversation_id,
                ConversationAccess.account_id,
            )
            .where(
                ConversationAccess.conversation_id.in_(conversation_ids),
                ConversationAccess.organization_id == organization_id,
            )
            .order_by(
                ConversationAccess.conversation_id,
                ConversationAccess.account_id,
            )
        )
        for conversation_id, account_id in rows:
            if account_id == owner_by_conversation.get(conversation_id):
                continue
            collaborators = grouped.get(conversation_id)
            if collaborators is not None:
                collaborators.append(account_id)
        return grouped

    async def replace_collaborators(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        owner_account_id: UUID,
        account_ids: list[UUID],
    ) -> None:
        await self._session.execute(
            delete(ConversationAccess).where(
                ConversationAccess.conversation_id == conversation_id,
                ConversationAccess.organization_id == organization_id,
                ConversationAccess.account_id != owner_account_id,
            )
        )
        self._session.add_all(
            ConversationAccess(
                conversation_id=conversation_id,
                organization_id=organization_id,
                account_id=account_id,
            )
            for account_id in account_ids
            if account_id != owner_account_id
        )
        await self._session.flush()
