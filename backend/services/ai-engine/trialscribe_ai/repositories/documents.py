"""Tenant-safe SQLAlchemy persistence for conversation documents."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from trialscribe_ai.models.document import Document
from trialscribe_ai.repositories import cursor as cursor_codec


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
            created_at, document_id = cursor_codec.decode_cursor(
                "created_at",
                cursor,
            )
            statement = statement.where(
                cursor_codec.before(
                    Document.created_at,
                    Document.id,
                    created_at,
                    document_id,
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
            next_cursor = cursor_codec.encode_cursor(
                "created_at",
                last.created_at,
                last.id,
            )
        return items, next_cursor

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()
