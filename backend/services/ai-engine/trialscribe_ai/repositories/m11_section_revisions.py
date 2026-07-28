"""Append-only SQLAlchemy persistence for M11 section revisions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.m11_section import M11Section
from trialscribe_ai.models.m11_section_revision import M11SectionRevision
from trialscribe_ai.utils.enum import M11RevisionAction


class M11SectionRevisionRepository:
    """Persist immutable section snapshots within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        section: M11Section,
        author_account_id: UUID,
        action: M11RevisionAction,
        created_at: datetime,
    ) -> M11SectionRevision:
        revision = M11SectionRevision(
            section_id=section.id,
            conversation_id=section.conversation_id,
            organization_id=section.organization_id,
            revision_number=section.current_revision,
            action=action.value,
            instructions=section.instructions,
            content=section.content,
            status=section.status,
            author_account_id=author_account_id,
            created_at=created_at,
            updated_at=created_at,
        )
        self._session.add(revision)
        await self._session.flush()
        return revision

    async def list_for_section(
        self,
        section_id: UUID,
        conversation_id: UUID,
        organization_id: UUID,
        *,
        after_revision: int,
        limit: int,
    ) -> tuple[list[M11SectionRevision], int | None]:
        result = list(
            await self._session.scalars(
                select(M11SectionRevision)
                .where(
                    M11SectionRevision.section_id == section_id,
                    M11SectionRevision.conversation_id == conversation_id,
                    M11SectionRevision.organization_id == organization_id,
                    M11SectionRevision.revision_number > after_revision,
                )
                .order_by(M11SectionRevision.revision_number)
                .limit(limit + 1)
            )
        )
        has_more = len(result) > limit
        items = result[:limit]
        next_after_revision = items[-1].revision_number if has_more and items else None
        return items, next_after_revision
