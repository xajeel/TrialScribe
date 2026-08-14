import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.pipelines.research_web import research_web_pipeline
from trialscribe_worker.providers.fake import (
    FakeChatProvider,
    FakeEmbeddingProvider,
    FakeFault,
    fake_vector_for,
)
from trialscribe_worker.providers.gateway import MemoryUsageRecorder, ProviderGateway
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.retrieval.research_types import ResearchHit
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.retrieval.web_allowlist import source_identity_for
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
    EVIDENCE_SOURCE_WEB,
    RESEARCH_QUERY_PARAMETER,
)
from trialscribe_worker.utils.enum import JobKind, ProviderOutcome
from trialscribe_worker.utils.exceptions import ProviderUnavailableError, ResearchSourceError

_HELPERS = importlib.util.spec_from_file_location(
    "research_web_evidence_helpers",
    Path(__file__).with_name("test_evidence_index.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_evidence_helpers = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_evidence_helpers)
MemoryChroma = _evidence_helpers.MemoryChroma
MemoryChunks = _evidence_helpers.MemoryChunks

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000901")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000902")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000903")
JOB_ID = UUID("00000000-0000-4000-8000-000000000904")
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/99999999/"
CDC_URL = "https://www.cdc.gov/farohealth-fixture"
EVIL_URL = "https://evil.example/x"
PUBMED_MARKER = "FAROHEALTH_PUBMED_MARKER"
WEB_MARKER = "FAROHEALTH_WEB_MARKER"
UPLOAD_MARKER = "FAROHEALTH_UPLOAD_MARKER"


class FakeSource:
    def __init__(
        self,
        hits: list[ResearchHit] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.hits = hits or []
        self.error = error
        self.calls = 0

    async def search(self, query: str, *, max_results: int) -> list[ResearchHit]:
        del query, max_results
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.hits)


async def _no_sleep(_seconds: float) -> None:
    return None


async def _never_cancelled() -> None:
    return None


def _gateway(embed: FakeEmbeddingProvider | None = None) -> ProviderGateway:
    return ProviderGateway(
        FakeChatProvider(),
        embed if embed is not None else FakeEmbeddingProvider(),
        WorkerSettings(provider_retry_attempts=1),
        MemoryUsageRecorder(),
        sleep=_no_sleep,
        rng=lambda: 0.0,
    )


def _evidence() -> EvidenceIndex:
    return EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )


def _hit(url: str, body: str, title: str = "Fixture") -> ResearchHit:
    return ResearchHit(url=url, title=title, published_on=None, body=body)


def _context(
    *,
    evidence: EvidenceIndex,
    gateway: ProviderGateway,
    pubmed: FakeSource,
    web: FakeSource,
) -> JobContext:
    reports: list[int] = []

    async def report(percent: int) -> None:
        reports.append(percent)

    return JobContext(
        job_id=JOB_ID,
        attempt=1,
        parameters={RESEARCH_QUERY_PARAMETER: "adult inclusion criteria"},
        report=report,
        check_cancelled=_never_cancelled,
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        gateway=gateway,
        evidence=evidence,
        research=SimpleNamespace(pubmed=pubmed, web=web),
        max_attempts=2,
    )


def test_research_web_kind_is_plain_text() -> None:
    assert JobKind.RESEARCH_WEB.value == "research_web"


def test_duplicate_urls_keep_the_pubmed_identity() -> None:
    evidence = _evidence()
    gateway = _gateway()
    asyncio.run(
        research_web_pipeline(
            _context(
                evidence=evidence,
                gateway=gateway,
                pubmed=FakeSource([_hit(PUBMED_URL, PUBMED_MARKER, "Paper")]),
                web=FakeSource([_hit(PUBMED_URL, WEB_MARKER, "Web copy")]),
            )
        )
    )
    identity = source_identity_for("https://pubmed.ncbi.nlm.nih.gov/99999999")
    found = asyncio.run(
        evidence.search(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            vector=fake_vector_for(PUBMED_MARKER),
            k=8,
        )
    )
    assert found
    assert {chunk.source_identity for chunk in found} == {identity}
    assert PUBMED_MARKER in found[0].text
    assert "Title:" in found[0].text
    assert WEB_MARKER not in found[0].text


def test_off_list_web_url_is_not_stored() -> None:
    evidence = _evidence()
    asyncio.run(
        research_web_pipeline(
            _context(
                evidence=evidence,
                gateway=_gateway(),
                pubmed=FakeSource(),
                web=FakeSource(
                    [
                        _hit(CDC_URL, WEB_MARKER),
                        _hit(EVIL_URL, "should not store"),
                    ]
                ),
            )
        )
    )
    evil_id = source_identity_for(EVIL_URL)
    cdc_id = source_identity_for(CDC_URL)
    found = asyncio.run(
        evidence.search(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            vector=fake_vector_for(WEB_MARKER),
            k=8,
        )
    )
    identities = {chunk.source_identity for chunk in found}
    assert cdc_id in identities
    assert evil_id not in identities


def test_pubmed_failure_still_stores_tavily_hit() -> None:
    evidence = _evidence()
    asyncio.run(
        research_web_pipeline(
            _context(
                evidence=evidence,
                gateway=_gateway(),
                pubmed=FakeSource(error=ResearchSourceError()),
                web=FakeSource([_hit(CDC_URL, WEB_MARKER)]),
            )
        )
    )
    found = asyncio.run(
        evidence.search(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            vector=fake_vector_for(WEB_MARKER),
            k=8,
        )
    )
    assert found
    assert found[0].source_kind == EVIDENCE_SOURCE_WEB
    assert found[0].source_identity == source_identity_for(CDC_URL)


def test_both_sources_failing_with_nothing_stored_raises() -> None:
    evidence = _evidence()
    with pytest.raises(ResearchSourceError):
        asyncio.run(
            research_web_pipeline(
                _context(
                    evidence=evidence,
                    gateway=_gateway(),
                    pubmed=FakeSource(error=ResearchSourceError()),
                    web=FakeSource(error=ResearchSourceError()),
                )
            )
        )


def test_uploaded_passage_survives_a_failed_research_job() -> None:
    evidence = _evidence()
    asyncio.run(
        evidence.put(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            text=UPLOAD_MARKER,
            vector=fake_vector_for(UPLOAD_MARKER),
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity="upload-1",
            start_char=0,
            end_char=len(UPLOAD_MARKER),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
    )
    with pytest.raises(ResearchSourceError):
        asyncio.run(
            research_web_pipeline(
                _context(
                    evidence=evidence,
                    gateway=_gateway(),
                    pubmed=FakeSource(error=ResearchSourceError()),
                    web=FakeSource(error=ResearchSourceError()),
                )
            )
        )
    found = asyncio.run(
        evidence.search(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            vector=fake_vector_for(UPLOAD_MARKER),
            k=8,
        )
    )
    assert [chunk.source_identity for chunk in found] == ["upload-1"]


def test_retrieve_twice_with_the_same_job_still_returns_vectors() -> None:
    evidence = _evidence()
    gateway = _gateway()
    asyncio.run(
        research_web_pipeline(
            _context(
                evidence=evidence,
                gateway=gateway,
                pubmed=FakeSource([_hit(PUBMED_URL, PUBMED_MARKER)]),
                web=FakeSource(),
            )
        )
    )
    retriever = ConversationRetriever(gateway, evidence, WorkerSettings())

    async def twice() -> tuple[list[str], list[str]]:
        first = await retriever.retrieve(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            query=PUBMED_MARKER,
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=8,
        )
        second = await retriever.retrieve(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            query=PUBMED_MARKER,
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=8,
        )
        return [chunk.text for chunk in first], [chunk.text for chunk in second]

    first_texts, second_texts = asyncio.run(twice())
    assert first_texts
    assert PUBMED_MARKER in first_texts[0]
    assert second_texts
    assert PUBMED_MARKER in second_texts[0]


def test_embed_failure_keeps_existing_web_passage() -> None:
    evidence = _evidence()
    identity = source_identity_for(CDC_URL)
    asyncio.run(
        evidence.put(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            text=WEB_MARKER,
            vector=fake_vector_for(WEB_MARKER),
            source_kind=EVIDENCE_SOURCE_WEB,
            source_identity=identity,
            start_char=0,
            end_char=len(WEB_MARKER),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
    )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            research_web_pipeline(
                _context(
                    evidence=evidence,
                    gateway=_gateway(
                        FakeEmbeddingProvider(
                            fault=FakeFault(
                                error=ProviderOutcome.ERROR,
                                fail_times=0,
                            )
                        )
                    ),
                    pubmed=FakeSource(),
                    web=FakeSource([_hit(CDC_URL, "replacement body")]),
                )
            )
        )
    found = asyncio.run(
        evidence.search(
            organization_id=ORGANIZATION_ID,
            conversation_id=CONVERSATION_ID,
            vector=fake_vector_for(WEB_MARKER),
            k=8,
        )
    )
    assert [chunk.source_identity for chunk in found] == [identity]
    assert WEB_MARKER in found[0].text
