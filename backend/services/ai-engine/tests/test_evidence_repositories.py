import asyncio
from dataclasses import fields
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from trialscribe_ai.models.evidence_chunk import EvidenceChunk
from trialscribe_ai.repositories.evidence_chunks import EvidenceChunkRepository

ORGANIZATION_ID = UUID("51000000-0000-4000-8000-000000000001")
CONVERSATION_ID = UUID("51000000-0000-4000-8000-000000000002")
FIRST_ID = UUID("51000000-0000-4000-8000-000000000011")
SECOND_ID = UUID("51000000-0000-4000-8000-000000000012")
FOREIGN_ID = UUID("51000000-0000-4000-8000-000000000099")


class MappingResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class ReturningSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statement: Any = None
        self.parameters: Any = None
        self.called = False

    async def execute(self, statement: Any, parameters: Any = None) -> MappingResult:
        self.called = True
        self.statement = statement
        self.parameters = parameters
        return MappingResult(self.rows)


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_model_has_no_foreign_keys() -> None:
    assert not hasattr(EvidenceChunk, "__table__")
    assert "ForeignKey" not in {field.name for field in fields(EvidenceChunk)}
    names = {field.name for field in fields(EvidenceChunk)}
    assert "embedding_model" not in names
    assert "embedding_dimensions" not in names


def test_get_scoped_filters_tenant_and_omits_embedding_columns() -> None:
    session = ReturningSession(
        [
            {
                "id": SECOND_ID,
                "organization_id": ORGANIZATION_ID,
                "conversation_id": CONVERSATION_ID,
                "source_kind": "web",
                "source_identity": "https://www.cdc.gov/x",
                "page_number": 1,
                "start_char": 0,
                "end_char": 8,
                "text": "CDC text",
            },
            {
                "id": FIRST_ID,
                "organization_id": ORGANIZATION_ID,
                "conversation_id": CONVERSATION_ID,
                "source_kind": "trial_data",
                "source_identity": "trial-1",
                "page_number": None,
                "start_char": 0,
                "end_char": 12,
                "text": "Age 18 years",
            },
        ]
    )
    repository = EvidenceChunkRepository(session)  # type: ignore[arg-type]

    rows = asyncio.run(
        repository.get_scoped(
            ORGANIZATION_ID,
            CONVERSATION_ID,
            [FIRST_ID, FOREIGN_ID, SECOND_ID],
        )
    )

    assert [row.id for row in rows] == [FIRST_ID, SECOND_ID]
    sql = compiled(session.statement).lower()
    assert "evidence_chunks" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "embedding_model" not in sql
    assert "embedding_dimensions" not in sql
    assert session.parameters["organization_id"] == ORGANIZATION_ID
    assert session.parameters["conversation_id"] == CONVERSATION_ID


def test_empty_id_list_does_not_query() -> None:
    session = ReturningSession([])
    repository = EvidenceChunkRepository(session)  # type: ignore[arg-type]

    rows = asyncio.run(repository.get_scoped(ORGANIZATION_ID, CONVERSATION_ID, []))

    assert rows == []
    assert session.called is False
