"""Persist and read protocol Word exports inside this tenant."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from trialscribe_worker.models.protocol_export import ProtocolExport
from trialscribe_worker.utils.constant import JOB_LIST_MAX_LIMIT


class ProtocolExportRepository:
    """Insert one export file, or read metadata and bytes, tenant-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        job_id: UUID,
        account_id: UUID,
        scope: str,
        filename: str,
        byte_size: int,
        content: bytes,
        section_count: int,
    ) -> None:
        """Store one assembled Word file for this job."""

        await self._session.execute(
            insert(ProtocolExport.__table__).values(
                id=uuid4(),
                organization_id=organization_id,
                conversation_id=conversation_id,
                job_id=job_id,
                account_id=account_id,
                scope=scope,
                filename=filename,
                byte_size=byte_size,
                content=content,
                section_count=section_count,
            )
        )

    async def list_metadata(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> list[ProtocolExport]:
        """List newest export facts for this conversation without file bytes."""

        statement = (
            select(ProtocolExport)
            .options(defer(ProtocolExport.content, raiseload=True))
            .where(
                ProtocolExport.organization_id == organization_id,
                ProtocolExport.conversation_id == conversation_id,
            )
            .order_by(ProtocolExport.created_at.desc(), ProtocolExport.id.desc())
            .limit(JOB_LIST_MAX_LIMIT)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def get_file(
        self,
        organization_id: UUID,
        export_id: UUID,
    ) -> tuple[str, bytes] | None:
        """Load filename and bytes for one export in this organization."""

        statement = select(ProtocolExport.filename, ProtocolExport.content).where(
            ProtocolExport.id == export_id,
            ProtocolExport.organization_id == organization_id,
        )
        row = (await self._session.execute(statement)).first()
        if row is None:
            return None
        return str(row[0]), bytes(row[1])
