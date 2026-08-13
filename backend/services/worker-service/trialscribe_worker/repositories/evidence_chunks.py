"""Read and write evidence_chunks with both tenant columns on every get."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.models.evidence_chunk import EvidenceChunk


class EvidenceChunkRepository:
    """Persist passage text within the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, chunk: EvidenceChunk) -> EvidenceChunk:
        """Store one passage so later hydration can load it by id."""

        self._session.add(chunk)
        await self._session.flush()
        return chunk

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        ids: list[UUID],
    ) -> list[EvidenceChunk]:
        """Load only the requested ids that belong to this organization and conversation.

        Ids that are missing or belong to another tenant are omitted, in the
        order the caller asked for them. An empty id list does not query.
        """

        if not ids:
            return []
        statement = select(EvidenceChunk).where(
            EvidenceChunk.id.in_(ids),
            EvidenceChunk.organization_id == organization_id,
            EvidenceChunk.conversation_id == conversation_id,
        )
        rows = list((await self._session.execute(statement)).scalars().all())
        by_id = {row.id: row for row in rows}
        return [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]
