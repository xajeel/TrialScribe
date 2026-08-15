import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from trialscribe_worker.models.m11_section_record import M11SectionListRecord
from trialscribe_worker.pipelines.export_protocol import (
    export_protocol_pipeline,
    parse_export_request,
)
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    EXPORT_SCOPE_DONE_ONLY,
    EXPORT_SCOPE_INCLUDE_DRAFTS,
    M11_SECTION_DONE_STATUS,
    M11_SECTION_DRAFT_STATUS,
)
from trialscribe_worker.utils.exceptions import InvalidJobInputError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000931")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000932")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000933")
JOB_ID = UUID("00000000-0000-4000-8000-000000000934")
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def test_parse_export_request_accepts_only_scope() -> None:
    assert parse_export_request({"scope": EXPORT_SCOPE_DONE_ONLY}) == EXPORT_SCOPE_DONE_ONLY
    assert (
        parse_export_request({"scope": EXPORT_SCOPE_INCLUDE_DRAFTS})
        == EXPORT_SCOPE_INCLUDE_DRAFTS
    )
    with pytest.raises(InvalidJobInputError):
        parse_export_request({})
    with pytest.raises(InvalidJobInputError):
        parse_export_request({"scope": EXPORT_SCOPE_DONE_ONLY, "extra": "no"})
    with pytest.raises(InvalidJobInputError):
        parse_export_request({"scope": "everything"})


def _section(number: str, status: str, content: str = "Body") -> M11SectionListRecord:
    return M11SectionListRecord(
        id=uuid4(),
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


def _pipeline_context(
    *,
    parameters: dict[str, object],
    sections: list[M11SectionListRecord],
    exports: list[dict[str, object]],
    snapshot: dict[str, object] | None,
    activity_at: datetime = NOW,
    conversation: tuple[str, datetime] | None = None,
) -> JobContext:
    async def report(percent: int) -> None:
        del percent

    async def never_cancelled() -> None:
        return None

    async def get_conversation(
        organization_id: UUID,
        conversation_id: UUID,
    ) -> tuple[str, datetime] | None:
        del organization_id, conversation_id
        if conversation is not None:
            return conversation
        return "AURORA-301", activity_at

    async def get_latest_readiness(
        organization_id: UUID,
        conversation_id: UUID,
    ) -> dict[str, object] | None:
        del organization_id, conversation_id
        return snapshot

    async def list_sections(
        organization_id: UUID,
        conversation_id: UUID,
    ) -> list[M11SectionListRecord]:
        del organization_id, conversation_id
        return sections

    async def list_chunks(
        organization_id: UUID,
        conversation_id: UUID,
        ids: list[UUID],
    ) -> list[Any]:
        del organization_id, conversation_id, ids
        return []

    async def add_export(**values: object) -> None:
        exports.append(values)

    return JobContext(
        job_id=JOB_ID,
        attempt=1,
        parameters=parameters,
        report=report,
        check_cancelled=never_cancelled,
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        generate=SimpleNamespace(
            get_conversation=get_conversation,
            get_latest_readiness=get_latest_readiness,
            list_sections=list_sections,
            list_chunks=list_chunks,
            add_export=add_export,
        ),
    )


def _ready_snapshot() -> dict[str, object]:
    return {"ready": True, "activity_at": NOW}


def test_missing_or_stale_readiness_is_rejected() -> None:
    exports: list[dict[str, object]] = []
    sections = [_section("1", M11_SECTION_DONE_STATUS)]
    missing = _pipeline_context(
        parameters={"scope": EXPORT_SCOPE_DONE_ONLY},
        sections=sections,
        exports=exports,
        snapshot=None,
    )
    with pytest.raises(InvalidJobInputError):
        asyncio.run(export_protocol_pipeline(missing))
    stale = _pipeline_context(
        parameters={"scope": EXPORT_SCOPE_DONE_ONLY},
        sections=sections,
        exports=exports,
        snapshot=_ready_snapshot(),
        activity_at=NOW + timedelta(minutes=1),
    )
    with pytest.raises(InvalidJobInputError):
        asyncio.run(export_protocol_pipeline(stale))
    assert exports == []


def test_done_only_requires_a_ready_snapshot() -> None:
    exports: list[dict[str, object]] = []
    context = _pipeline_context(
        parameters={"scope": EXPORT_SCOPE_DONE_ONLY},
        sections=[_section("1", M11_SECTION_DONE_STATUS)],
        exports=exports,
        snapshot={"ready": False, "activity_at": NOW},
    )
    with pytest.raises(InvalidJobInputError):
        asyncio.run(export_protocol_pipeline(context))
    assert exports == []


def test_include_drafts_may_run_when_not_ready() -> None:
    exports: list[dict[str, object]] = []
    context = _pipeline_context(
        parameters={"scope": EXPORT_SCOPE_INCLUDE_DRAFTS},
        sections=[_section("1", M11_SECTION_DRAFT_STATUS)],
        exports=exports,
        snapshot={"ready": False, "activity_at": NOW},
    )
    asyncio.run(export_protocol_pipeline(context))
    assert len(exports) == 1
    assert exports[0]["organization_id"] == ORGANIZATION_ID
    assert exports[0]["conversation_id"] == CONVERSATION_ID
    assert exports[0]["section_count"] == 1
    assert exports[0]["scope"] == EXPORT_SCOPE_INCLUDE_DRAFTS


def test_done_only_with_zero_done_sections_is_rejected() -> None:
    exports: list[dict[str, object]] = []
    context = _pipeline_context(
        parameters={"scope": EXPORT_SCOPE_DONE_ONLY},
        sections=[_section("1", M11_SECTION_DRAFT_STATUS)],
        exports=exports,
        snapshot=_ready_snapshot(),
    )
    with pytest.raises(InvalidJobInputError):
        asyncio.run(export_protocol_pipeline(context))
    assert exports == []


def test_successful_done_only_stores_one_export() -> None:
    exports: list[dict[str, object]] = []
    context = _pipeline_context(
        parameters={"scope": EXPORT_SCOPE_DONE_ONLY},
        sections=[
            _section("1", M11_SECTION_DONE_STATUS),
            _section("2", M11_SECTION_DRAFT_STATUS),
        ],
        exports=exports,
        snapshot=_ready_snapshot(),
    )
    asyncio.run(export_protocol_pipeline(context))
    assert len(exports) == 1
    assert exports[0]["organization_id"] == ORGANIZATION_ID
    assert exports[0]["conversation_id"] == CONVERSATION_ID
    assert exports[0]["job_id"] == JOB_ID
    assert exports[0]["account_id"] == ACCOUNT_ID
    assert exports[0]["section_count"] == 1
    assert str(exports[0]["filename"]).endswith(".docx")
    assert int(exports[0]["byte_size"]) > 0
