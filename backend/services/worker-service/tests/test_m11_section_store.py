import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from trialscribe_worker.repositories.conversation_memory import ConversationMemoryStore
from trialscribe_worker.repositories.m11_sections import M11SectionStore

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000701")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000702")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000703")
NOW = datetime(2026, 8, 14, tzinfo=UTC)


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
    return str(statement.compile(dialect=postgresql.dialect())).lower()


def test_get_scoped_sql_names_both_tenant_columns() -> None:
    session = RecordingSession()
    store = M11SectionStore(session)  # type: ignore[arg-type]
    try:
        asyncio.run(store.get_scoped(ORGANIZATION_ID, CONVERSATION_ID, "5"))
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "trialscribe.m11_sections" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert session.parameters[0]["organization_id"] == ORGANIZATION_ID
    assert session.parameters[0]["conversation_id"] == CONVERSATION_ID
    assert session.parameters[0]["section_number"] == "5"


def test_revise_draft_sql_updates_activity_and_inserts_revision() -> None:
    class MultiSession:
        def __init__(self) -> None:
            self.statements: list[Any] = []
            self.parameters: list[Any] = []

        async def execute(self, statement: Any, parameters: Any = None) -> Any:
            self.statements.append(statement)
            self.parameters.append(parameters)
            if len(self.statements) == 1:

                class _Result:
                    def mappings(self) -> Any:
                        class _Map:
                            def first(self) -> dict[str, Any]:
                                return {
                                    "id": UUID("00000000-0000-4000-8000-000000000799"),
                                    "instructions": "",
                                    "content": "Adults aged 18 years or older.",
                                    "current_revision": 1,
                                }

                        return _Map()

                return _Result()
            if len(self.statements) >= 3:
                raise _Captured
            return None

    session = MultiSession()
    store = M11SectionStore(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            store.revise_draft(
                ORGANIZATION_ID,
                CONVERSATION_ID,
                "5",
                expected_revision=0,
                content="Adults aged 18 years or older.",
                author_account_id=ACCOUNT_ID,
                now=NOW,
            )
        )
    except _Captured:
        pass
    update_sql = compiled(session.statements[0])
    activity_sql = compiled(session.statements[1])
    assert "update" in update_sql
    assert "trialscribe.m11_sections" in update_sql
    assert "organization_id" in update_sql
    assert "conversation_id" in update_sql
    assert "last_activity_at" in activity_sql
    assert "trialscribe.conversations" in activity_sql
    assert "organization_id" in activity_sql
    assert "conversation_id" in activity_sql
    insert_sql = compiled(session.statements[2])
    assert "insert" in insert_sql
    assert "m11_section_revisions" in insert_sql
    assert session.parameters[2]["action"] == "revised"


def test_revise_draft_can_record_a_generated_action() -> None:
    class MultiSession:
        def __init__(self) -> None:
            self.parameters: list[Any] = []

        async def execute(self, statement: Any, parameters: Any = None) -> Any:
            self.parameters.append(parameters)
            if len(self.parameters) == 1:

                class _Result:
                    def mappings(self) -> Any:
                        class _Map:
                            def first(self) -> dict[str, Any]:
                                return {
                                    "id": UUID("00000000-0000-4000-8000-000000000799"),
                                    "instructions": "",
                                    "content": "Adults aged 18 years or older.",
                                    "current_revision": 1,
                                }

                        return _Map()

                return _Result()
            if len(self.parameters) >= 3:
                raise _Captured
            return None

    session = MultiSession()
    store = M11SectionStore(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            store.revise_draft(
                ORGANIZATION_ID,
                CONVERSATION_ID,
                "5",
                expected_revision=0,
                content="Adults aged 18 years or older.",
                author_account_id=ACCOUNT_ID,
                now=NOW,
                action="generated",
            )
        )
    except _Captured:
        pass
    assert session.parameters[2]["action"] == "generated"


def test_recent_memory_sql_names_both_tenant_columns() -> None:
    session = RecordingSession()
    store = ConversationMemoryStore(session)  # type: ignore[arg-type]
    try:
        asyncio.run(store.recent(ORGANIZATION_ID, CONVERSATION_ID, 8))
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "trialscribe.conversation_messages" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "sequence" in sql


def test_store_modules_do_not_import_ai_engine() -> None:
    root = Path(__file__).resolve().parents[1] / "trialscribe_worker" / "repositories"
    assert "trialscribe_ai" not in (root / "m11_sections.py").read_text(encoding="utf-8")
    assert "trialscribe_ai" not in (root / "conversation_memory.py").read_text(
        encoding="utf-8"
    )
