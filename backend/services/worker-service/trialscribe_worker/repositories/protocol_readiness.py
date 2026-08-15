"""Persist and read protocol readiness snapshots inside this tenant."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.models.protocol_readiness_check import ProtocolReadinessCheck

_GET_CONVERSATION = text(
    "SELECT title, last_activity_at FROM trialscribe.conversations "
    "WHERE id = :conversation_id AND organization_id = :organization_id"
)
_GET_LATEST = text(
    "SELECT id, organization_id, conversation_id, job_id, ready, computed_at, "
    "activity_at, protocol_title, summary, issues, sections "
    "FROM trialscribe.protocol_readiness_checks "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "ORDER BY computed_at DESC LIMIT 1"
)


class ProtocolReadinessRepository:
    """Insert one check, or read the newest snapshot, tenant-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> tuple[str, datetime] | None:
        """Load title and activity for this organization and conversation."""

        result = await self._session.execute(
            _GET_CONVERSATION,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return str(row["title"]), row["last_activity_at"]

    async def add(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        job_id: UUID,
        ready: bool,
        computed_at: datetime,
        activity_at: datetime,
        protocol_title: str,
        summary: dict[str, object],
        issues: list[object],
        sections: list[object],
    ) -> None:
        """Store one scored snapshot for this job."""

        await self._session.execute(
            insert(ProtocolReadinessCheck.__table__).values(
                id=uuid4(),
                organization_id=organization_id,
                conversation_id=conversation_id,
                job_id=job_id,
                ready=ready,
                computed_at=computed_at,
                activity_at=activity_at,
                protocol_title=protocol_title,
                summary=summary,
                issues=issues,
                sections=sections,
            )
        )

    async def get_latest(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> dict[str, object] | None:
        """Return the newest snapshot, or None when this protocol has none."""

        result = await self._session.execute(
            _GET_LATEST,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return dict(row)
