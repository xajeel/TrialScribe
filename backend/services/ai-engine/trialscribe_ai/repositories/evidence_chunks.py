"""Read tenant-scoped evidence passages without loading embedding columns."""

from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.evidence_chunk import EvidenceChunk

_GET_SCOPED = text(
    "SELECT id, organization_id, conversation_id, source_kind, source_identity, "
    "page_number, start_char, end_char, text "
    "FROM trialscribe.evidence_chunks "
    "WHERE id IN :ids "
    "AND organization_id = :organization_id "
    "AND conversation_id = :conversation_id"
).bindparams(bindparam("ids", expanding=True))


class EvidenceChunkRepository:
    """Load cited passages that belong to this organization and conversation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        ids: list[UUID],
    ) -> list[EvidenceChunk]:
        """Return requested ids that belong to this tenant, in request order.

        Missing or foreign ids are omitted. An empty id list does not query.
        """

        if not ids:
            return []
        result = await self._session.execute(
            _GET_SCOPED,
            {
                "ids": ids,
                "organization_id": organization_id,
                "conversation_id": conversation_id,
            },
        )
        by_id = {
            row["id"]: EvidenceChunk(
                id=row["id"],
                organization_id=row["organization_id"],
                conversation_id=row["conversation_id"],
                source_kind=row["source_kind"],
                source_identity=row["source_identity"],
                page_number=row["page_number"],
                start_char=row["start_char"],
                end_char=row["end_char"],
                text=row["text"],
            )
            for row in result.mappings()
        }
        return [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]
