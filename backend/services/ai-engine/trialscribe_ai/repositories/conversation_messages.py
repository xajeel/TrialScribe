"""Append-only SQLAlchemy persistence for conversation messages."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.conversation_message import ConversationMessage
from trialscribe_ai.repositories import cursor as cursor_codec


class ConversationMessageRepository:
    """Persist messages within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        author_account_id: UUID | None,
        role: str,
        content: str,
        activity_at: datetime,
    ) -> ConversationMessage:
        current = await self._session.scalar(
            select(func.max(ConversationMessage.sequence)).where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.organization_id == organization_id,
            )
        )
        message = ConversationMessage(
            conversation_id=conversation_id,
            organization_id=organization_id,
            author_account_id=author_account_id,
            role=role,
            content=content,
            sequence=(current or 0) + 1,
            created_at=activity_at,
            updated_at=activity_at,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ConversationMessage], str | None]:
        statement = select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.organization_id == organization_id,
        )
        if cursor is not None:
            statement = statement.where(
                ConversationMessage.sequence > cursor_codec.decode_sequence_cursor(cursor)
            )
        result = list(
            await self._session.scalars(
                statement.order_by(ConversationMessage.sequence).limit(limit + 1)
            )
        )
        has_more = len(result) > limit
        items = result[:limit]
        next_cursor = None
        if has_more and items:
            next_cursor = cursor_codec.encode_sequence_cursor(items[-1].sequence)
        return items, next_cursor
