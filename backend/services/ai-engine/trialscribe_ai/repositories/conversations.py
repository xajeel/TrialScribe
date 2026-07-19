"""Tenant-safe SQLAlchemy persistence for conversations."""

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.conversation_access import ConversationAccess
from trialscribe_ai.utils.exceptions import InvalidCursorError


def _encode_cursor(activity_at: datetime, conversation_id: UUID) -> str:
    payload = json.dumps(
        {"activity_at": activity_at.isoformat(), "id": str(conversation_id)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(cursor + padding, altchars=b"-_", validate=True))
        if set(payload) != {"activity_at", "id"}:
            raise ValueError
        activity_at = datetime.fromisoformat(payload["activity_at"])
        if activity_at.tzinfo is None:
            raise ValueError
        return activity_at, UUID(payload["id"])
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursorError from None


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
            activity_at, conversation_id = _decode_cursor(cursor)
            statement = statement.where(
                or_(
                    Conversation.last_activity_at < activity_at,
                    and_(
                        Conversation.last_activity_at == activity_at,
                        Conversation.id < conversation_id,
                    ),
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
            next_cursor = _encode_cursor(last.last_activity_at, last.id)
        return items, next_cursor

    async def flush(self, conversation: Conversation) -> Conversation:
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation
