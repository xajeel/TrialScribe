"""Tenant-scoped SQLAlchemy persistence for current M11 sections."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.config.m11_catalog import (
    M11_CATALOG_VERSION,
    M11SectionDefinition,
)
from trialscribe_ai.models.m11_section import M11Section


class M11SectionRepository:
    """Persist current M11 section state within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_catalog(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        definitions: Sequence[M11SectionDefinition],
    ) -> list[M11Section]:
        sections = [
            M11Section(
                conversation_id=conversation_id,
                organization_id=organization_id,
                catalog_version=M11_CATALOG_VERSION,
                section_number=definition.number,
                title=definition.title,
                position=definition.position,
                instructions="",
                content="",
                status="draft",
                current_revision=0,
            )
            for definition in definitions
        ]
        self._session.add_all(sections)
        await self._session.flush()
        return sections

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        organization_id: UUID,
    ) -> list[M11Section]:
        return list(
            await self._session.scalars(
                select(M11Section)
                .where(
                    M11Section.conversation_id == conversation_id,
                    M11Section.organization_id == organization_id,
                )
                .order_by(M11Section.position)
            )
        )

    async def get_by_number(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        section_number: str,
        *,
        for_update: bool = False,
    ) -> M11Section | None:
        statement = select(M11Section).where(
            M11Section.conversation_id == conversation_id,
            M11Section.organization_id == organization_id,
            M11Section.section_number == section_number,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def flush(self, section: M11Section) -> M11Section:
        await self._session.flush()
        await self._session.refresh(section)
        return section
