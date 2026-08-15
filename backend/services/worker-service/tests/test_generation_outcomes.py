import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from trialscribe_worker.repositories.generation_outcomes import (
    GenerationAttemptOutcome,
    GenerationOutcomeRepository,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000701")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000702")
JOB_ID = UUID("00000000-0000-4000-8000-000000000703")
FIRST_CITE = UUID("00000000-0000-4000-8000-000000000711")
SECOND_CITE = UUID("00000000-0000-4000-8000-000000000712")


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

    async def execute(self, statement: Any, parameters: Any = None) -> MappingResult:
        self.statement = statement
        self.parameters = parameters
        return MappingResult(self.rows)


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_list_latest_select_omits_prompt_and_content() -> None:
    session = ReturningSession([])
    repository = GenerationOutcomeRepository(session)  # type: ignore[arg-type]

    asyncio.run(repository.list_latest_for_job(ORGANIZATION_ID, CONVERSATION_ID, JOB_ID))

    sql = compiled(session.statement).lower()
    assert "trialscribe.section_generation_attempts" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "job_id" in sql
    assert "section_number" in sql
    assert "error_code" in sql
    assert "citation_ids" in sql
    assert "prompt" not in sql
    assert "content" not in sql
    assert session.parameters == {
        "organization_id": ORGANIZATION_ID,
        "conversation_id": CONVERSATION_ID,
        "job_id": JOB_ID,
    }


def test_list_latest_keeps_the_greatest_attempt_per_section() -> None:
    session = ReturningSession(
        [
            {
                "section_number": "5",
                "status": "failed",
                "error_code": "provider_failed",
                "citation_ids": [FIRST_CITE],
                "attempt": 2,
            },
            {
                "section_number": "1",
                "status": "succeeded",
                "error_code": None,
                "citation_ids": [str(SECOND_CITE)],
                "attempt": 1,
            },
            {
                "section_number": "5",
                "status": "failed",
                "error_code": "empty_output",
                "citation_ids": [],
                "attempt": 1,
            },
        ]
    )
    repository = GenerationOutcomeRepository(session)  # type: ignore[arg-type]

    rows = asyncio.run(
        repository.list_latest_for_job(ORGANIZATION_ID, CONVERSATION_ID, JOB_ID)
    )

    assert rows == [
        GenerationAttemptOutcome(
            section_number="5",
            status="failed",
            error_code="provider_failed",
            citation_ids=[FIRST_CITE],
            attempt=2,
        ),
        GenerationAttemptOutcome(
            section_number="1",
            status="succeeded",
            error_code=None,
            citation_ids=[SECOND_CITE],
            attempt=1,
        ),
    ]


def test_rewrite_options_select_omits_prompt() -> None:
    session = ReturningSession([])
    repository = GenerationOutcomeRepository(session)  # type: ignore[arg-type]

    asyncio.run(repository.get_rewrite_options(ORGANIZATION_ID, CONVERSATION_ID, JOB_ID))

    sql = compiled(session.statement).lower()
    assert "trialscribe.section_generation_attempts" in sql
    assert "content" in sql
    assert "prompt" not in sql
    assert session.parameters == {
        "organization_id": ORGANIZATION_ID,
        "conversation_id": CONVERSATION_ID,
        "job_id": JOB_ID,
    }


def test_rewrite_options_parse_the_latest_succeeded_json() -> None:
    session = ReturningSession(
        [
            {
                "content": "not json",
                "status": "succeeded",
                "attempt": 3,
            },
            {
                "content": (
                    '{"kind":"rewrite_options","items":['
                    '{"id":"alternative-1","text":"Keep the same length."},'
                    '{"id":"alternative-2","text":"Tighten the wording."}'
                    "]}"
                ),
                "status": "succeeded",
                "attempt": 2,
            },
            {
                "content": '{"kind":"rewrite_options","items":[]}',
                "status": "failed",
                "attempt": 1,
            },
        ]
    )
    repository = GenerationOutcomeRepository(session)  # type: ignore[arg-type]

    rows = asyncio.run(
        repository.get_rewrite_options(ORGANIZATION_ID, CONVERSATION_ID, JOB_ID)
    )

    assert rows == [
        ("alternative-1", "Keep the same length."),
        ("alternative-2", "Tighten the wording."),
    ]


def test_rewrite_options_are_empty_when_content_is_not_options_json() -> None:
    session = ReturningSession(
        [
            {
                "content": "First draft of section 5.",
                "status": "succeeded",
                "attempt": 1,
            }
        ]
    )
    repository = GenerationOutcomeRepository(session)  # type: ignore[arg-type]

    rows = asyncio.run(
        repository.get_rewrite_options(ORGANIZATION_ID, CONVERSATION_ID, JOB_ID)
    )

    assert rows == []
