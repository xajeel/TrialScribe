"""Persist section generation attempts inside the caller's transaction."""

from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.models.section_generation_attempt import SectionGenerationAttempt


class SectionGenerationAttemptRepository:
    """Insert one per-section generation record."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        job_id: UUID,
        attempt: int,
        section_number: str,
        status: str,
        model: str | None = None,
        prompt: str | None = None,
        content: str | None = None,
        error_code: str | None = None,
        citation_ids: list[str] | None = None,
    ) -> None:
        """Store the outcome of one section on this job attempt."""

        await self._session.execute(
            insert(SectionGenerationAttempt.__table__).values(
                id=uuid4(),
                organization_id=organization_id,
                conversation_id=conversation_id,
                job_id=job_id,
                attempt=attempt,
                section_number=section_number,
                status=status,
                model=model,
                prompt=prompt,
                content=content,
                error_code=error_code,
                citation_ids=citation_ids or [],
            )
        )
