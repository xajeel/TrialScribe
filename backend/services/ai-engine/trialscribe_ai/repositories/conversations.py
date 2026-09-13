"""Tenant-safe SQLAlchemy persistence for conversations."""

from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.conversation_access import ConversationAccess
from trialscribe_ai.repositories import cursor as cursor_codec


class ConversationRepository:
    """Persist conversations within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _access_filter(organization_id: UUID, account_id: UUID) -> object:
        granted = exists(
            select(ConversationAccess.id).where(
                ConversationAccess.conversation_id == Conversation.id,
                ConversationAccess.organization_id == organization_id,
                ConversationAccess.account_id == account_id,
            )
        )
        return and_(
            Conversation.organization_id == organization_id,
            or_(Conversation.owner_account_id == account_id, granted),
        )

    async def add(self, conversation: Conversation) -> Conversation:
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            self._access_filter(organization_id, account_id),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def list_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        *,
        archived: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Conversation], str | None]:
        archive_filter = (
            Conversation.archived_at.is_not(None)
            if archived
            else Conversation.archived_at.is_(None)
        )
        statement = select(Conversation).where(
            self._access_filter(organization_id, account_id),
            archive_filter,
        )
        if cursor is not None:
            activity_at, conversation_id = cursor_codec.decode_cursor(
                "activity_at",
                cursor,
            )
            statement = statement.where(
                cursor_codec.before(
                    Conversation.last_activity_at,
                    Conversation.id,
                    activity_at,
                    conversation_id,
                )
            )
        result = list(
            await self._session.scalars(
                statement.order_by(
                    Conversation.last_activity_at.desc(),
                    Conversation.id.desc(),
                ).limit(limit + 1)
            )
        )
        has_more = len(result) > limit
        items = result[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = cursor_codec.encode_cursor(
                "activity_at",
                last.last_activity_at,
                last.id,
            )
        return items, next_cursor

    async def flush(self, conversation: Conversation) -> Conversation:
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation
