"""Append-only SQLAlchemy persistence for conversation messages."""

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.conversation_message import ConversationMessage
from trialscribe_ai.utils.exceptions import InvalidCursorError


def _encode_cursor(sequence: int) -> str:
    payload = json.dumps({"sequence": sequence}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(cursor + padding, altchars=b"-_", validate=True))
        if set(payload) != {"sequence"}:
            raise ValueError
        sequence = payload["sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError
        return sequence
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursorError from None


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
                ConversationMessage.sequence > _decode_cursor(cursor)
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
            next_cursor = _encode_cursor(items[-1].sequence)
        return items, next_cursor
