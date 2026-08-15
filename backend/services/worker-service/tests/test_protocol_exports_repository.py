import asyncio
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects import postgresql

from trialscribe_worker.repositories.protocol_exports import ProtocolExportRepository

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000901")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000902")
EXPORT_ID = UUID("00000000-0000-4000-8000-000000000903")


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
    return str(statement.compile(dialect=postgresql.dialect()))


def test_list_metadata_is_tenant_scoped_and_omits_content() -> None:
    session = RecordingSession()
    repository = ProtocolExportRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(repository.list_metadata(ORGANIZATION_ID, CONVERSATION_ID))
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert re.search(r"\bprotocol_exports\.content\b", sql) is None


def test_get_file_is_tenant_scoped() -> None:
    session = RecordingSession()
    repository = ProtocolExportRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(repository.get_file(ORGANIZATION_ID, EXPORT_ID))
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "organization_id" in sql
    assert "id" in sql


def test_add_inserts_tenant_and_job_columns() -> None:
    session = RecordingSession()
    repository = ProtocolExportRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            repository.add(
                organization_id=ORGANIZATION_ID,
                conversation_id=CONVERSATION_ID,
                job_id=uuid4(),
                account_id=uuid4(),
                scope="done-only",
                filename="protocol.docx",
                byte_size=12,
                content=b"PK\x03\x04fake",
                section_count=1,
            )
        )
    except _Captured:
        pass
    sql = compiled(session.statements[0]).lower()
    assert "insert" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "content" in sql
