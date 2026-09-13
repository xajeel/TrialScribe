import asyncio
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects import postgresql

from trialscribe_worker.models.section_generation_attempt import SectionGenerationAttempt
from trialscribe_worker.repositories.section_generation_attempts import (
    SectionGenerationAttemptRepository,
)
from trialscribe_worker.utils.enum import GenerationAttemptStatus

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000801")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000802")
JOB_ID = UUID("00000000-0000-4000-8000-000000000803")


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, parameters: Any = None) -> Any:
        del parameters
        self.statements.append(statement)
        raise _Captured


class _Captured(Exception):
    pass


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect())).lower()


def test_the_model_declares_no_foreign_key_it_cannot_resolve() -> None:
    declared = [
        column.name
        for column in SectionGenerationAttempt.__table__.columns
        if column.foreign_keys
    ]
    assert declared == []


def test_add_inserts_tenant_scoped_generation_attempt() -> None:
    session = RecordingSession()
    repository = SectionGenerationAttemptRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            repository.add(
                organization_id=ORGANIZATION_ID,
                conversation_id=CONVERSATION_ID,
                job_id=JOB_ID,
                attempt=1,
                section_number="5",
                status=GenerationAttemptStatus.SUCCEEDED.value,
                model="fake-chat",
                prompt="system...",
                content="draft",
                citation_ids=[str(uuid4())],
            )
        )
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "insert" in sql
    assert "section_generation_attempts" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
