import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from trialscribe_events.contracts.document import DocumentDeleted, DocumentUploaded
from trialscribe_events.envelope import EventEnvelope
from trialscribe_worker.pipelines.document_events import (
    handle_document_deleted,
    handle_document_uploaded,
)
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
    INDEX_DOCUMENT_PARAMETER,
)
from trialscribe_worker.utils.enum import JobKind

_HELPERS = importlib.util.spec_from_file_location(
    "rag_document_event_helpers",
    Path(__file__).with_name("test_evidence_index.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_evidence_helpers = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_evidence_helpers)
MemoryChroma = _evidence_helpers.MemoryChroma
MemoryChunks = _evidence_helpers.MemoryChunks

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000901")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000902")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000903")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000904")
NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


class RecordingJobs:
    def __init__(self) -> None:
        self.requests: list[tuple[UUID, UUID, JobCreateRequest, datetime]] = []

    async def request_job(
        self,
        organization_id: UUID,
        account_id: UUID,
        request: JobCreateRequest,
        now: datetime,
    ) -> None:
        self.requests.append((organization_id, account_id, request, now))


def _envelope(event_type: str) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        event_version=1,
        occurred_at=NOW,
        organization_id=ORGANIZATION_ID,
        subject=str(DOCUMENT_ID),
        correlation_id=uuid4(),
        producer="ai-engine",
        payload={},
    )


def test_uploaded_handler_requests_an_index_document_job() -> None:
    jobs = RecordingJobs()
    payload = DocumentUploaded(
        document_id=DOCUMENT_ID,
        conversation_id=CONVERSATION_ID,
        organization_id=ORGANIZATION_ID,
        uploaded_by_account_id=ACCOUNT_ID,
        kind="research_document",
    )
    asyncio.run(
        handle_document_uploaded(
            _envelope("document.uploaded"),
            payload,
            session=object(),  # type: ignore[arg-type]
            jobs=jobs,  # type: ignore[arg-type]
        )
    )
    assert len(jobs.requests) == 1
    organization_id, account_id, request, occurred = jobs.requests[0]
    assert organization_id == ORGANIZATION_ID
    assert account_id == ACCOUNT_ID
    assert request.kind == JobKind.INDEX_DOCUMENT.value
    assert request.conversation_id == CONVERSATION_ID
    assert request.parameters == {INDEX_DOCUMENT_PARAMETER: str(DOCUMENT_ID)}
    assert occurred == NOW


def test_deleted_handler_drops_that_source_for_the_tenant() -> None:
    evidence = EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )

    async def scenario() -> int:
        await evidence.put(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            text="keep-me-not",
            vector=[0.1] * DEFAULT_EMBEDDING_DIMENSIONS,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=str(DOCUMENT_ID),
            start_char=0,
            end_char=10,
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
        payload = DocumentDeleted(
            document_id=DOCUMENT_ID,
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
        )
        await handle_document_deleted(
            _envelope("document.deleted"),
            payload,
            session=object(),  # type: ignore[arg-type]
            evidence=evidence,
        )
        remaining = await evidence.search(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            vector=[0.1] * DEFAULT_EMBEDDING_DIMENSIONS,
            k=5,
        )
        return len(remaining)

    assert asyncio.run(scenario()) == 0
