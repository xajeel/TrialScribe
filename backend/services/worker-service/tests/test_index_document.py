import asyncio
import importlib.util
from pathlib import Path
from uuid import UUID

import pytest

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.source_document import SourceDocument
from trialscribe_worker.pipelines.index_document import index_document_pipeline
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider, FakeFault
from trialscribe_worker.providers.gateway import MemoryUsageRecorder, ProviderGateway
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    INDEX_DOCUMENT_PARAMETER,
    INDEX_EMPTY_TEXT_ERROR,
    INDEX_FAILED_ERROR,
)
from trialscribe_worker.utils.enum import JobKind, ProviderOutcome
from trialscribe_worker.utils.exceptions import ProviderUnavailableError

_HELPERS = importlib.util.spec_from_file_location(
    "rag_index_evidence_helpers",
    Path(__file__).with_name("test_evidence_index.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_evidence_helpers = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_evidence_helpers)
MemoryChroma = _evidence_helpers.MemoryChroma
MemoryChunks = _evidence_helpers.MemoryChunks

PHRASE = "FAROHEALTH_INCLUSION_AGE_18 is required."
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000801")
OTHER_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000802")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000803")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000804")
OTHER_CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000805")
JOB_ID = UUID("00000000-0000-4000-8000-000000000806")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000807")


class MemorySources:
    def __init__(self, document: SourceDocument | None) -> None:
        self.document = document
        self.marks: list[tuple[str, str | None]] = []

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
    ) -> SourceDocument | None:
        document = self.document
        if document is None:
            return None
        if (
            document.organization_id != organization_id
            or document.conversation_id != conversation_id
            or document.id != document_id
        ):
            return None
        return document

    async def mark_status(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
        status: str,
        error: str | None,
    ) -> bool:
        del organization_id, conversation_id, document_id
        self.marks.append((status, error))
        return True


async def _no_sleep(_seconds: float) -> None:
    return None


async def _never_cancelled() -> None:
    return None


def _document(content: bytes, content_type: str = "text/plain") -> SourceDocument:
    return SourceDocument(
        id=DOCUMENT_ID,
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        kind="research_document",
        content_type=content_type,
        status="pending",
        error=None,
        content=content,
    )


def _context(
    *,
    sources: MemorySources,
    evidence: EvidenceIndex,
    gateway: ProviderGateway,
    attempt: int = 1,
    max_attempts: int = 2,
    conversation_id: UUID | None = CONVERSATION_ID,
) -> JobContext:
    reports: list[int] = []

    async def report(percent: int) -> None:
        reports.append(percent)

    context = JobContext(
        job_id=JOB_ID,
        attempt=attempt,
        parameters={INDEX_DOCUMENT_PARAMETER: str(DOCUMENT_ID)},
        report=report,
        check_cancelled=_never_cancelled,
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        conversation_id=conversation_id,
        gateway=gateway,
        evidence=evidence,
        sources=sources,
        max_attempts=max_attempts,
    )
    return context


def _gateway(embed: FakeEmbeddingProvider | None = None) -> ProviderGateway:
    return ProviderGateway(
        FakeChatProvider(),
        embed or FakeEmbeddingProvider(),
        WorkerSettings(provider_retry_attempts=1),
        MemoryUsageRecorder(),
        sleep=_no_sleep,
        rng=lambda: 0.0,
    )


def test_index_document_kind_is_plain_text() -> None:
    assert JobKind.INDEX_DOCUMENT.value == "index_document"


def test_indexing_a_text_file_makes_the_phrase_retrievable() -> None:
    sources = MemorySources(_document(PHRASE.encode("utf-8")))
    evidence = EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )
    gateway = _gateway()
    retriever = ConversationRetriever(gateway, evidence, WorkerSettings())

    asyncio.run(index_document_pipeline(_context(sources=sources, evidence=evidence, gateway=gateway)))

    assert sources.marks[-1] == ("ready", None)
    found = asyncio.run(
        retriever.retrieve(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            query="FAROHEALTH_INCLUSION_AGE_18",
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=3,
        )
    )
    assert len(found) == 1
    assert "FAROHEALTH_INCLUSION_AGE_18" in found[0].text
    assert found[0].source_identity == str(DOCUMENT_ID)

    asyncio.run(index_document_pipeline(_context(sources=sources, evidence=evidence, gateway=gateway)))
    again = asyncio.run(
        retriever.retrieve(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            query="FAROHEALTH_INCLUSION_AGE_18",
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=8,
        )
    )
    assert [chunk.source_identity for chunk in again] == [str(DOCUMENT_ID)]

    foreign = asyncio.run(
        retriever.retrieve(
            organization_id=OTHER_ORGANIZATION_ID,
            conversation_id=OTHER_CONVERSATION_ID,
            query="FAROHEALTH_INCLUSION_AGE_18",
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=3,
        )
    )
    assert foreign == []


def test_empty_extract_marks_failed_without_raising() -> None:
    sources = MemorySources(_document(b"   "))
    evidence = EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )
    asyncio.run(
        index_document_pipeline(
            _context(sources=sources, evidence=evidence, gateway=_gateway())
        )
    )
    assert sources.marks == [("failed", INDEX_EMPTY_TEXT_ERROR)]


def test_embed_fault_marks_failed_only_on_the_last_attempt() -> None:
    sources = MemorySources(_document(PHRASE.encode("utf-8")))
    evidence = EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )
    embed = FakeEmbeddingProvider(
        fault=FakeFault(error=ProviderOutcome.ERROR, fail_times=0)
    )
    gateway = _gateway(embed)
    first = _context(
        sources=sources,
        evidence=evidence,
        gateway=gateway,
        attempt=1,
        max_attempts=2,
    )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(index_document_pipeline(first))
    assert sources.marks == []

    second = _context(
        sources=sources,
        evidence=evidence,
        gateway=gateway,
        attempt=2,
        max_attempts=2,
    )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(index_document_pipeline(second))
    assert sources.marks == [("failed", INDEX_FAILED_ERROR)]
