"""Read and update documents rows with both tenant columns on every statement."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.models.source_document import SourceDocument

_GET_SCOPED = text(
    "SELECT id, organization_id, conversation_id, kind, content_type, status, "
    "error, content FROM trialscribe.documents WHERE id = :document_id "
    "AND organization_id = :organization_id "
    "AND conversation_id = :conversation_id"
)
_MARK_STATUS = text(
    "UPDATE trialscribe.documents SET status = :status, error = :error, "
    "updated_at = NOW() WHERE id = :document_id "
    "AND organization_id = :organization_id "
    "AND conversation_id = :conversation_id"
)


class SourceDocumentRepository:
    """Look up one file, or record whether indexing finished, inside this tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
    ) -> SourceDocument | None:
        """Load one file that belongs to this organization and conversation."""

        result = await self._session.execute(
            _GET_SCOPED,
            {
                "document_id": document_id,
                "organization_id": organization_id,
                "conversation_id": conversation_id,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return SourceDocument(
            id=row["id"],
            organization_id=row["organization_id"],
            conversation_id=row["conversation_id"],
            kind=row["kind"],
            content_type=row["content_type"],
            status=row["status"],
            error=row["error"],
            content=bytes(row["content"]),
        )

    async def mark_status(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
        status: str,
        error: str | None,
    ) -> bool:
        """Set processing status without loading the file bytes."""

        result = await self._session.execute(
            _MARK_STATUS,
            {
                "document_id": document_id,
                "organization_id": organization_id,
                "conversation_id": conversation_id,
                "status": status,
                "error": error,
            },
        )
        return bool(result.rowcount)
