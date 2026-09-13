"""Read recent conversation turns with both tenant columns on every statement."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_RECENT = text(
    "SELECT role, content FROM trialscribe.conversation_messages "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "ORDER BY sequence DESC "
    "LIMIT :limit"
)


class ConversationMemoryStore:
    """Return the latest bounded window of conversation messages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recent(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> list[tuple[str, str]]:
        """Return up to `limit` turns, oldest first."""

        result = await self._session.execute(
            _RECENT,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
                "limit": limit,
            },
        )
        rows = list(result.mappings())
        rows.reverse()
        return [(str(row["role"]), str(row["content"])) for row in rows]
