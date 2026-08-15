"""Assemble a stored ICH M11 Word file without changing chapter text."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.m11_sections import M11SectionStore
from trialscribe_worker.repositories.protocol_exports import ProtocolExportRepository
from trialscribe_worker.repositories.protocol_readiness import ProtocolReadinessRepository
from trialscribe_worker.retrieval.citations import parse_cite_ids
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.services.protocol_docx import build_protocol_docx, export_filename
from trialscribe_worker.utils.constant import (
    EXPORT_SCOPE_DONE_ONLY,
    EXPORT_SCOPE_INCLUDE_DRAFTS,
    EXPORT_SCOPE_PARAMETER,
    M11_SECTION_DONE_STATUS,
    M11_SECTION_DRAFT_STATUS,
)
from trialscribe_worker.utils.exceptions import InvalidJobInputError, WorkerServiceError


def parse_export_request(parameters: dict[str, object]) -> str:
    """Return the export scope, or refuse anything else."""

    if set(parameters) != {EXPORT_SCOPE_PARAMETER}:
        raise InvalidJobInputError
    scope = parameters[EXPORT_SCOPE_PARAMETER]
    if scope not in {EXPORT_SCOPE_DONE_ONLY, EXPORT_SCOPE_INCLUDE_DRAFTS}:
        raise InvalidJobInputError
    return str(scope)


def _is_stale(activity_at: datetime, snapshot_activity: object) -> bool:
    if not isinstance(snapshot_activity, datetime):
        return True
    return activity_at > snapshot_activity


async def export_protocol_pipeline(context: JobContext) -> None:
    """Build one Word file and store it without editing chapters."""

    if context.generate is None:
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    scope = parse_export_request(context.parameters)
    stores = context.generate
    get_conversation = getattr(stores, "get_conversation", None)
    get_latest_readiness = getattr(stores, "get_latest_readiness", None)
    list_sections = getattr(stores, "list_sections", None)
    list_chunks = getattr(stores, "list_chunks", None)
    add_export = getattr(stores, "add_export", None)
    if not all(
        callable(item)
        for item in (
            get_conversation,
            get_latest_readiness,
            list_sections,
            list_chunks,
            add_export,
        )
    ):
        raise WorkerServiceError
    await context.report(10)
    await context.check_cancelled()
    conversation = await get_conversation(
        context.organization_id,
        context.conversation_id,
    )
    if conversation is None:
        raise InvalidJobInputError
    protocol_title, activity_at = conversation
    snapshot = await get_latest_readiness(
        context.organization_id,
        context.conversation_id,
    )
    if snapshot is None or _is_stale(activity_at, snapshot.get("activity_at")):
        raise InvalidJobInputError
    if scope == EXPORT_SCOPE_DONE_ONLY and not bool(snapshot.get("ready")):
        raise InvalidJobInputError
    sections = await list_sections(context.organization_id, context.conversation_id)
    if scope == EXPORT_SCOPE_DONE_ONLY:
        included = [row for row in sections if row.status == M11_SECTION_DONE_STATUS]
    else:
        included = [
            row
            for row in sections
            if row.status in {M11_SECTION_DONE_STATUS, M11_SECTION_DRAFT_STATUS}
        ]
    if not included:
        raise InvalidJobInputError
    cite_ids: list[UUID] = []
    seen: set[UUID] = set()
    for row in included:
        for cite_id in parse_cite_ids(row.content):
            if cite_id in seen:
                continue
            seen.add(cite_id)
            cite_ids.append(cite_id)
    await context.report(50)
    await context.check_cancelled()
    chunks = await list_chunks(
        context.organization_id,
        context.conversation_id,
        cite_ids,
    )
    exported_at = datetime.now(UTC)
    payload = build_protocol_docx(
        protocol_title=protocol_title,
        exported_at=exported_at,
        scope=scope,
        sections=included,
        chunks=list(chunks),
    )
    await context.report(90)
    await context.check_cancelled()
    await add_export(
        organization_id=context.organization_id,
        conversation_id=context.conversation_id,
        job_id=context.job_id,
        account_id=context.account_id,
        scope=scope,
        filename=export_filename(protocol_title, exported_at),
        byte_size=len(payload),
        content=payload,
        section_count=len(included),
    )
    await context.report(100)


def bind_export_stores(context: JobContext, session: object) -> None:
    """Attach tenant-scoped stores for one database session."""

    sections = M11SectionStore(session)  # type: ignore[arg-type]
    chunks = EvidenceChunkRepository(session)  # type: ignore[arg-type]
    readiness = ProtocolReadinessRepository(session)  # type: ignore[arg-type]
    exports = ProtocolExportRepository(session)  # type: ignore[arg-type]
    context.generate = SimpleNamespace(
        get_conversation=readiness.get_conversation,
        get_latest_readiness=readiness.get_latest,
        list_sections=sections.list_scoped,
        list_chunks=chunks.get_scoped,
        add_export=exports.add,
    )


async def run_export_protocol_job(
    context: JobContext,
    runtime: DatabaseRuntime,
) -> None:
    """Load live chapters and persist one Word export."""

    if context.conversation_id is None:
        raise InvalidJobInputError
    parse_export_request(context.parameters)
    async with runtime.transaction() as session:
        bind_export_stores(context, session)
        await export_protocol_pipeline(context)
