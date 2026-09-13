import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from trialscribe_worker.models.m11_section_record import M11SectionListRecord
from trialscribe_worker.models.protocol_readiness_check import ProtocolReadinessCheck
from trialscribe_worker.models.source_document import SourceDocumentMetadata
from trialscribe_worker.pipelines.validate_readiness import (
    evaluate_readiness,
    parse_validate_request,
    validate_readiness_pipeline,
)
from trialscribe_worker.repositories.generation_outcomes import GenerationAttemptOutcome
from trialscribe_worker.repositories.source_documents import SourceDocumentRepository
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import GENERATE_SECTION_NUMBERS
from trialscribe_worker.utils.exceptions import InvalidJobInputError, JobCancelledError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000801")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000802")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000803")
JOB_ID = UUID("00000000-0000-4000-8000-000000000804")
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
CITE = UUID("00000000-0000-4000-8000-000000000811")
MISSING_CITE = UUID("00000000-0000-4000-8000-000000000812")


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


def _section(
    number: str,
    *,
    status: str = "done",
    content: str = "Adults aged 18 years or older.",
    section_id: UUID | None = None,
) -> M11SectionListRecord:
    return M11SectionListRecord(
        id=section_id or uuid4(),
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        section_number=number,
        title=f"Section {number}",
        position=int(number),
        content=content,
        status=status,
        current_revision=1,
        updated_at=NOW,
    )


def _catalog(**overrides: M11SectionListRecord) -> list[M11SectionListRecord]:
    rows = {
        number: _section(number) for number in sorted(GENERATE_SECTION_NUMBERS, key=int)
    }
    rows.update({row.section_number: row for row in overrides.values()})
    if overrides:
        for row in overrides.values():
            rows[row.section_number] = row
    return [rows[number] for number in sorted(rows, key=int)]


def test_list_metadata_omits_content_and_names_both_tenant_columns() -> None:
    session = RecordingSession()
    repository = SourceDocumentRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(repository.list_metadata(ORGANIZATION_ID, CONVERSATION_ID))
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "trialscribe.documents" in sql
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "filename" in sql
    assert "content" not in sql
    assert session.parameters[0]["organization_id"] == ORGANIZATION_ID
    assert session.parameters[0]["conversation_id"] == CONVERSATION_ID


def test_all_done_ready_sources_and_resolved_cites_are_ready() -> None:
    cited = f"Inclusion requires consent [cite:{CITE}]."
    snapshot = evaluate_readiness(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        activity_at=NOW,
        sections=_catalog(s5=_section("5", content=cited)),
        documents=[
            SourceDocumentMetadata(
                id=uuid4(),
                filename="protocol.pdf",
                status="ready",
                updated_at=NOW,
            )
        ],
        attempts={},
        allowed_citation_ids={CITE},
    )
    assert snapshot["ready"] is True
    summary = snapshot["summary"]
    assert isinstance(summary, dict)
    assert summary["done_sections"] == 14
    assert summary["pending_sources"] == 0
    citations = summary["citations"]
    assert isinstance(citations, dict)
    assert citations["needing_review"] == 0


def test_one_draft_is_not_ready() -> None:
    snapshot = evaluate_readiness(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        activity_at=NOW,
        sections=_catalog(s5=_section("5", status="draft")),
        documents=[],
        attempts={},
        allowed_citation_ids=set(),
    )
    assert snapshot["ready"] is False
    issues = snapshot["issues"]
    assert isinstance(issues, list)
    assert any(item["code"] == "section_not_done" for item in issues)


def test_pending_upload_is_not_ready() -> None:
    snapshot = evaluate_readiness(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        activity_at=NOW,
        sections=_catalog(),
        documents=[
            SourceDocumentMetadata(
                id=uuid4(),
                filename="pending.pdf",
                status="pending",
                updated_at=NOW,
            )
        ],
        attempts={},
        allowed_citation_ids=set(),
    )
    assert snapshot["ready"] is False
    issues = snapshot["issues"]
    assert isinstance(issues, list)
    assert any(item["code"] == "source_pending" for item in issues)


def test_failed_latest_attempt_on_a_draft_is_a_generation_issue() -> None:
    snapshot = evaluate_readiness(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        activity_at=NOW,
        sections=_catalog(s6=_section("6", status="draft", content="Draft wording.")),
        documents=[],
        attempts={
            "6": GenerationAttemptOutcome(
                section_number="6",
                status="failed",
                error_code="provider_failed",
                citation_ids=[],
                attempt=1,
            )
        },
        allowed_citation_ids=set(),
    )
    assert snapshot["ready"] is False
    issues = snapshot["issues"]
    assert isinstance(issues, list)
    assert any(item["id"] == "generation-failed-6" for item in issues)


def test_unresolved_citation_is_not_ready() -> None:
    snapshot = evaluate_readiness(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        activity_at=NOW,
        sections=_catalog(
            s9=_section("9", content=f"Needs a source [cite:{MISSING_CITE}].")
        ),
        documents=[],
        attempts={},
        allowed_citation_ids={CITE},
    )
    assert snapshot["ready"] is False
    issues = snapshot["issues"]
    assert isinstance(issues, list)
    assert any(item["code"] == "unresolved_citation" for item in issues)


def test_done_section_ignores_an_older_failed_attempt() -> None:
    snapshot = evaluate_readiness(
        protocol_title="AURORA-301",
        protocol_id=CONVERSATION_ID,
        activity_at=NOW,
        sections=_catalog(),
        documents=[],
        attempts={
            "5": GenerationAttemptOutcome(
                section_number="5",
                status="failed",
                error_code="provider_failed",
                citation_ids=[],
                attempt=1,
            )
        },
        allowed_citation_ids=set(),
    )
    assert snapshot["ready"] is True
    issues = snapshot["issues"]
    assert isinstance(issues, list)
    assert issues == []


def test_the_snapshot_model_declares_no_foreign_key_it_cannot_resolve() -> None:
    declared = [
        column.name
        for column in ProtocolReadinessCheck.__table__.columns
        if column.foreign_keys
    ]
    assert declared == []


def test_extra_parameters_are_rejected() -> None:
    with pytest.raises(InvalidJobInputError):
        parse_validate_request({"mode": "rewrite"})
    parse_validate_request({})


def _pipeline_context(
    *,
    sections: list[M11SectionListRecord],
    snapshots: list[dict[str, object]],
    check_cancelled: Any = None,
) -> JobContext:
    async def report(percent: int) -> None:
        del percent

    async def never_cancelled() -> None:
        return None

    async def get_conversation(organization_id: UUID, conversation_id: UUID) -> tuple[str, datetime]:
        del organization_id, conversation_id
        return "AURORA-301", NOW

    async def list_sections(organization_id: UUID, conversation_id: UUID) -> list[M11SectionListRecord]:
        del organization_id, conversation_id
        return sections

    async def list_documents(
        organization_id: UUID, conversation_id: UUID
    ) -> list[SourceDocumentMetadata]:
        del organization_id, conversation_id
        return []

    async def latest_attempts(
        organization_id: UUID, conversation_id: UUID
    ) -> dict[str, GenerationAttemptOutcome]:
        del organization_id, conversation_id
        return {}

    async def list_chunks(
        organization_id: UUID, conversation_id: UUID, ids: list[UUID]
    ) -> list[SimpleNamespace]:
        del organization_id, conversation_id
        return [SimpleNamespace(id=item) for item in ids]

    async def add_snapshot(**values: object) -> None:
        snapshots.append(values)

    return JobContext(
        job_id=JOB_ID,
        attempt=1,
        parameters={},
        report=report,
        check_cancelled=check_cancelled or never_cancelled,
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        generate=SimpleNamespace(
            get_conversation=get_conversation,
            list_sections=list_sections,
            list_documents=list_documents,
            latest_attempts=latest_attempts,
            list_chunks=list_chunks,
            add_snapshot=add_snapshot,
        ),
    )


def test_succeeded_job_inserts_ready_without_changing_section_content() -> None:
    sections = _catalog()
    original = [row.content for row in sections]
    snapshots: list[dict[str, object]] = []
    context = _pipeline_context(sections=sections, snapshots=snapshots)
    asyncio.run(validate_readiness_pipeline(context))
    assert snapshots[0]["ready"] is True
    assert [row.content for row in sections] == original


def test_cancel_before_insert_stores_nothing() -> None:
    sections = _catalog()
    original = [row.content for row in sections]
    snapshots: list[dict[str, object]] = []
    checks = {"count": 0}

    async def check_cancelled() -> None:
        checks["count"] += 1
        if checks["count"] >= 3:
            raise JobCancelledError

    context = _pipeline_context(
        sections=sections,
        snapshots=snapshots,
        check_cancelled=check_cancelled,
    )
    with pytest.raises(JobCancelledError):
        asyncio.run(validate_readiness_pipeline(context))
    assert snapshots == []
    assert [row.content for row in sections] == original
