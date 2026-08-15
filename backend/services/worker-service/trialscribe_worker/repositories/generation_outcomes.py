"""Read the latest per-section generation outcome without loading prompts."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LIST_FOR_JOB = text(
    "SELECT section_number, status, error_code, citation_ids, attempt "
    "FROM trialscribe.section_generation_attempts "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "AND job_id = :job_id "
    "ORDER BY attempt DESC"
)


@dataclass(frozen=True)
class GenerationAttemptOutcome:
    """Public columns of one generation attempt row."""

    section_number: str
    status: str
    error_code: str | None
    citation_ids: list[UUID]
    attempt: int


def _citation_ids(value: object) -> list[UUID]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        return []
    return [item if isinstance(item, UUID) else UUID(str(item)) for item in value]


class GenerationOutcomeRepository:
    """Load the newest attempt per section for one job, tenant-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_latest_for_job(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        job_id: UUID,
    ) -> list[GenerationAttemptOutcome]:
        """Return the highest-attempt row per section_number.

        The statement never selects `prompt` or `content` (B4).
        """

        result = await self._session.execute(
            _LIST_FOR_JOB,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
                "job_id": job_id,
            },
        )
        latest: dict[str, GenerationAttemptOutcome] = {}
        for row in result.mappings():
            number = str(row["section_number"])
            if number in latest:
                continue
            latest[number] = GenerationAttemptOutcome(
                section_number=number,
                status=str(row["status"]),
                error_code=row["error_code"],
                citation_ids=_citation_ids(row["citation_ids"]),
                attempt=int(row["attempt"]),
            )
        return list(latest.values())
