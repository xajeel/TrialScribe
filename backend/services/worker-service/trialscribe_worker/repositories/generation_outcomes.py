"""Read the latest per-section generation outcome without loading prompts."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.utils.constant import REWRITE_OPTIONS_KIND

_LIST_FOR_JOB = text(
    "SELECT section_number, status, error_code, citation_ids, attempt "
    "FROM trialscribe.section_generation_attempts "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "AND job_id = :job_id "
    "ORDER BY attempt DESC"
)
_LATEST_BY_SECTION = text(
    "SELECT DISTINCT ON (section_number) section_number, status, error_code, "
    "citation_ids, attempt "
    "FROM trialscribe.section_generation_attempts "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "ORDER BY section_number, created_at DESC"
)
_REWRITE_OPTIONS = text(
    "SELECT content, status, attempt "
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

    async def latest_by_section(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> dict[str, GenerationAttemptOutcome]:
        """Return the newest attempt per section across every job.

        The statement never selects `prompt` or `content` (B4).
        """

        result = await self._session.execute(
            _LATEST_BY_SECTION,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
            },
        )
        latest: dict[str, GenerationAttemptOutcome] = {}
        for row in result.mappings():
            number = str(row["section_number"])
            latest[number] = GenerationAttemptOutcome(
                section_number=number,
                status=str(row["status"]),
                error_code=row["error_code"],
                citation_ids=_citation_ids(row["citation_ids"]),
                attempt=int(row["attempt"]),
            )
        return latest

    async def get_rewrite_options(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        job_id: UUID,
    ) -> list[tuple[str, str]]:
        """Return rewrite option texts for the newest succeeded rewrite attempt.

        The statement never selects `prompt` (B4).
        """

        result = await self._session.execute(
            _REWRITE_OPTIONS,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
                "job_id": job_id,
            },
        )
        for row in result.mappings():
            if str(row["status"]) != "succeeded":
                continue
            payload = _rewrite_items(row["content"])
            if payload is not None:
                return payload
        return []


def _rewrite_items(value: object) -> list[tuple[str, str]] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or parsed.get("kind") != REWRITE_OPTIONS_KIND:
        return None
    items = parsed.get("items")
    if not isinstance(items, list):
        return None
    options: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        option_id = item.get("id")
        text = item.get("text")
        if not isinstance(option_id, str) or not isinstance(text, str):
            return None
        options.append((option_id, text))
    return options
