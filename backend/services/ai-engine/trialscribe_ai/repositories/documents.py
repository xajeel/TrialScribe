"""Tenant-safe SQLAlchemy persistence for conversation documents."""

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from trialscribe_ai.models.document import Document
from trialscribe_ai.utils.exceptions import InvalidCursorError


def _encode_cursor(created_at: datetime, document_id: UUID) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(document_id)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(cursor + padding, altchars=b"-_", validate=True))
        if set(payload) != {"created_at", "id"}:
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, UUID(payload["id"])
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursorError from None


class DocumentRepository:
    """Persist documents within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
    ) -> Document | None:
        statement = select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.conversation_id == conversation_id,
        )
        return await self._session.scalar(statement)

    async def list_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Document], str | None]:
        statement = (
            select(Document)
            .options(defer(Document.content, raiseload=True))
            .where(
                Document.organization_id == organization_id,
                Document.conversation_id == conversation_id,
            )
        )
        if cursor is not None:
            created_at, document_id = _decode_cursor(cursor)
            statement = statement.where(
                or_(
                    Document.created_at < created_at,
                    and_(
                        Document.created_at == created_at,
                        Document.id < document_id,
                    ),
                )
            )
        result = list(
            await self._session.scalars(
                statement.order_by(
                    Document.created_at.desc(),
                    Document.id.desc(),
                ).limit(limit + 1)
            )
        )
        has_more = len(result) > limit
        items = result[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)
        return items, next_cursor

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()
