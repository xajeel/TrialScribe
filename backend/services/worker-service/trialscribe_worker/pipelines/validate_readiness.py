"""Score whether a protocol is ready to export without changing chapter text."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.models.m11_section_record import M11SectionListRecord
from trialscribe_worker.models.source_document import SourceDocumentMetadata
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.generation_outcomes import (
    GenerationAttemptOutcome,
    GenerationOutcomeRepository,
)
from trialscribe_worker.repositories.m11_sections import M11SectionStore
from trialscribe_worker.repositories.protocol_readiness import ProtocolReadinessRepository
from trialscribe_worker.repositories.source_documents import SourceDocumentRepository
from trialscribe_worker.retrieval.citations import parse_cite_ids
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    GENERATE_SECTION_NUMBERS,
    M11_SECTION_DONE_STATUS,
    M11_SECTION_DRAFT_STATUS,
)
from trialscribe_worker.utils.enum import GenerationAttemptStatus
from trialscribe_worker.utils.exceptions import InvalidJobInputError, WorkerServiceError

_CATALOG = tuple(sorted(GENERATE_SECTION_NUMBERS, key=int))


def _word_count(content: str) -> int:
    trimmed = content.strip()
    return 0 if trimmed == "" else len(trimmed.split())


def _iso(value: datetime) -> str:
    return value.isoformat()


def _issue(
    *,
    issue_id: str,
    title: str,
    detail: str,
    severity: str,
    code: str,
    action: str,
    action_label: str,
    section_number: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": issue_id,
        "title": title,
        "detail": detail,
        "severity": severity,
        "code": code,
        "action": action,
        "action_label": action_label,
    }
    if section_number is not None:
        payload["section_number"] = section_number
    return payload


def evaluate_readiness(
    *,
    protocol_title: str,
    protocol_id: UUID,
    activity_at: datetime,
    sections: list[M11SectionListRecord],
    documents: list[SourceDocumentMetadata],
    attempts: dict[str, GenerationAttemptOutcome],
    allowed_citation_ids: set[UUID],
) -> dict[str, object]:
    """Return a JSON-ready snapshot. Never writes chapters or sources."""

    issues: list[dict[str, object]] = []
    by_number = {row.section_number: row for row in sections}
    section_views: list[dict[str, object]] = []
    citation_resolved = 0
    citation_review = 0
    timestamps = [activity_at]

    for number in _CATALOG:
        row = by_number.get(number)
        if row is None:
            issues.append(
                _issue(
                    issue_id=f"section-missing-{number}",
                    title="Required section is missing",
                    detail=f"Section {number} is not in this protocol.",
                    severity="error",
                    code="missing_section",
                    action="open-section",
                    action_label="Open section",
                    section_number=number,
                )
            )
            continue
        timestamps.append(row.updated_at)
        section_issues: list[dict[str, object]] = []
        if row.status != M11_SECTION_DONE_STATUS:
            item = _issue(
                issue_id=f"section-not-done-{row.id}",
                title="Section is not marked done",
                detail=f"{row.section_number} · {row.title}",
                severity="error",
                code="section_not_done",
                action="open-section",
                action_label="Open section",
                section_number=row.section_number,
            )
            section_issues.append(item)
            issues.append(item)
        if row.content.strip() == "":
            item = _issue(
                issue_id=f"empty-section-{row.id}",
                title="Section has no content",
                detail=f"{row.section_number} · {row.title}",
                severity="warning"
                if row.status == M11_SECTION_DRAFT_STATUS
                else "error",
                code="empty_section",
                action="open-section",
                action_label="Open section",
                section_number=row.section_number,
            )
            section_issues.append(item)
            issues.append(item)
        attempt = attempts.get(row.section_number)
        if (
            row.status == M11_SECTION_DRAFT_STATUS
            and attempt is not None
            and attempt.status == GenerationAttemptStatus.FAILED.value
        ):
            item = _issue(
                issue_id=f"generation-failed-{row.section_number}",
                title="Generation completed with an issue",
                detail=f"{row.section_number} · {row.title}",
                severity="error",
                code="generation_failed",
                action="retry-check",
                action_label="Check again",
                section_number=row.section_number,
            )
            section_issues.append(item)
            issues.append(item)
        cite_ids = parse_cite_ids(row.content)
        unresolved = [cite_id for cite_id in cite_ids if cite_id not in allowed_citation_ids]
        citation_resolved += len(cite_ids) - len(unresolved)
        citation_review += len(unresolved)
        for cite_id in unresolved:
            item = _issue(
                issue_id=f"citation-unresolved-{row.section_number}-{cite_id}",
                title="Citation evidence unavailable",
                detail=f"Section {row.section_number} · Citation [cite:{cite_id}]",
                severity="error",
                code="unresolved_citation",
                action="review-citation",
                action_label="Open citation",
                section_number=row.section_number,
            )
            section_issues.append(item)
            issues.append(item)
        section_views.append(
            {
                "id": str(row.id),
                "section_number": row.section_number,
                "title": row.title,
                "position": row.position,
                "status": row.status,
                "revision": row.current_revision,
                "words": _word_count(row.content),
                "updated_at": _iso(row.updated_at),
                "content": row.content,
                "issues": section_issues,
                "citations": {
                    "resolved": len(cite_ids) - len(unresolved),
                    "needing_review": len(unresolved),
                },
            }
        )

    ready_sources = 0
    pending_sources = 0
    failed_sources = 0
    for document in documents:
        timestamps.append(document.updated_at)
        if document.status == "ready":
            ready_sources += 1
        elif document.status == "pending":
            pending_sources += 1
            issues.append(
                _issue(
                    issue_id=f"source-pending-{document.id}",
                    title="Source processing is not complete",
                    detail=document.filename,
                    severity="warning",
                    code="source_pending",
                    action="view-sources",
                    action_label="View sources",
                )
            )
        elif document.status == "failed":
            failed_sources += 1
            issues.append(
                _issue(
                    issue_id=f"source-failed-{document.id}",
                    title="Source could not be prepared",
                    detail=document.filename,
                    severity="error",
                    code="source_failed",
                    action="view-sources",
                    action_label="View sources",
                )
            )

    done_sections = sum(
        1 for row in sections if row.status == M11_SECTION_DONE_STATUS
    )
    ready = (
        len(by_number) == len(_CATALOG)
        and done_sections == len(_CATALOG)
        and all(row.content.strip() != "" for row in sections)
        and pending_sources == 0
        and failed_sources == 0
        and citation_review == 0
        and not any(item["code"] == "generation_failed" for item in issues)
    )
    return {
        "ready": ready,
        "protocol_title": protocol_title,
        "protocol_id": str(protocol_id),
        "summary": {
            "total_sections": len(_CATALOG),
            "done_sections": done_sections,
            "draft_sections": len(sections) - done_sections,
            "ready_sources": ready_sources,
            "pending_sources": pending_sources,
            "failed_sources": failed_sources,
            "latest_activity": _iso(max(timestamps)),
            "citations": {
                "resolved": citation_resolved,
                "needing_review": citation_review,
            },
        },
        "issues": issues,
        "sections": section_views,
    }


def parse_validate_request(parameters: dict[str, object]) -> None:
    """Refuse any job parameters; the conversation is already on the ticket."""

    if parameters:
        raise InvalidJobInputError


async def validate_readiness_pipeline(context: JobContext) -> None:
    """Score the live protocol and insert one snapshot without editing chapters."""

    if context.generate is None:
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    parse_validate_request(context.parameters)
    stores = context.generate
    get_conversation = getattr(stores, "get_conversation", None)
    list_sections = getattr(stores, "list_sections", None)
    list_documents = getattr(stores, "list_documents", None)
    latest_attempts = getattr(stores, "latest_attempts", None)
    list_chunks = getattr(stores, "list_chunks", None)
    add_snapshot = getattr(stores, "add_snapshot", None)
    if not all(
        callable(item)
        for item in (
            get_conversation,
            list_sections,
            list_documents,
            latest_attempts,
            list_chunks,
            add_snapshot,
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
    sections = await list_sections(context.organization_id, context.conversation_id)
    documents = await list_documents(context.organization_id, context.conversation_id)
    attempts = await latest_attempts(context.organization_id, context.conversation_id)
    cite_ids: list[UUID] = []
    seen: set[UUID] = set()
    for row in sections:
        for cite_id in parse_cite_ids(row.content):
            if cite_id in seen:
                continue
            seen.add(cite_id)
            cite_ids.append(cite_id)
    chunks = await list_chunks(
        context.organization_id,
        context.conversation_id,
        cite_ids,
    )
    await context.check_cancelled()
    snapshot = evaluate_readiness(
        protocol_title=protocol_title,
        protocol_id=context.conversation_id,
        activity_at=activity_at,
        sections=list(sections),
        documents=list(documents),
        attempts=dict(attempts),
        allowed_citation_ids={chunk.id for chunk in chunks},
    )
    await context.check_cancelled()
    await add_snapshot(
        organization_id=context.organization_id,
        conversation_id=context.conversation_id,
        job_id=context.job_id,
        ready=bool(snapshot["ready"]),
        computed_at=datetime.now(UTC),
        activity_at=activity_at,
        protocol_title=protocol_title,
        summary=snapshot["summary"],
        issues=snapshot["issues"],
        sections=snapshot["sections"],
    )
    await context.report(100)


def bind_readiness_stores(context: JobContext, session: object) -> None:
    """Attach tenant-scoped stores for one database session."""

    sections = M11SectionStore(session)  # type: ignore[arg-type]
    documents = SourceDocumentRepository(session)  # type: ignore[arg-type]
    attempts = GenerationOutcomeRepository(session)  # type: ignore[arg-type]
    chunks = EvidenceChunkRepository(session)  # type: ignore[arg-type]
    readiness = ProtocolReadinessRepository(session)  # type: ignore[arg-type]
    context.generate = SimpleNamespace(
        get_conversation=readiness.get_conversation,
        list_sections=sections.list_scoped,
        list_documents=documents.list_metadata,
        latest_attempts=attempts.latest_by_section,
        list_chunks=chunks.get_scoped,
        add_snapshot=readiness.add,
    )


async def run_validate_readiness_job(
    context: JobContext,
    runtime: DatabaseRuntime,
) -> None:
    """Load live facts and persist one readiness snapshot."""

    if context.conversation_id is None:
        raise InvalidJobInputError
    parse_validate_request(context.parameters)
    async with runtime.transaction() as session:
        bind_readiness_stores(context, session)
        await validate_readiness_pipeline(context)

