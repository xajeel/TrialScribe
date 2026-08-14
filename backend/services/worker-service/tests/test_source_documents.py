import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from trialscribe_worker.repositories.source_documents import SourceDocumentRepository

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000601")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000602")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000603")


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []
        self.parameters: list[Any] = []

    async def execute(self, statement: Any, parameters: Any = None) -> Any:
        self.statements.append(statement)
        self.parameters.append(parameters)
        raise _Captured


class _Captured(Exception):
    pass


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_get_scoped_sql_names_all_three_keys() -> None:
    session = RecordingSession()
    repository = SourceDocumentRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(repository.get_scoped(ORGANIZATION_ID, CONVERSATION_ID, DOCUMENT_ID))
    except _Captured:
        pass
    sql = compiled(session.statements[0]).lower()
    assert "trialscribe.documents" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "content" in sql
    assert session.parameters[0]["document_id"] == DOCUMENT_ID
    assert session.parameters[0]["organization_id"] == ORGANIZATION_ID
    assert session.parameters[0]["conversation_id"] == CONVERSATION_ID


def test_mark_status_sql_updates_without_selecting_content() -> None:
    session = RecordingSession()
    repository = SourceDocumentRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            repository.mark_status(
                ORGANIZATION_ID,
                CONVERSATION_ID,
                DOCUMENT_ID,
                "ready",
                None,
            )
        )
    except _Captured:
        pass
    sql = compiled(session.statements[0]).lower()
    assert "update" in sql
    assert "trialscribe.documents" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "status" in sql
    assert "select" not in sql
    assert "content" not in sql
