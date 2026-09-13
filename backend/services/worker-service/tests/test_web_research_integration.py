import asyncio
import importlib.util
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from trialscribe_worker.providers.fake import fake_vector_for
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.retrieval.chroma_index import EvidenceIndex
from trialscribe_worker.retrieval.research_types import ResearchHit
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.retrieval.web_allowlist import source_identity_for
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
    EVIDENCE_SOURCE_WEB,
    RESEARCH_QUERY_PARAMETER,
)
from trialscribe_worker.utils.enum import JobKind, JobStatus
from trialscribe_worker.utils.exceptions import JobAttemptFailedError, ResearchSourceError

_HELPERS = importlib.util.spec_from_file_location(
    "web_research_runtime_helpers",
    Path(__file__).with_name("test_ai_runtime_integration.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_runtime = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_runtime)
Backbone = _runtime.Backbone
CONSUME_TIMEOUT_SECONDS = _runtime.CONSUME_TIMEOUT_SECONDS
with_backbone = _runtime.with_backbone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_AI_RUNTIME_INTEGRATION") != "1",
        reason="requires the isolated PostgreSQL, Redis, Kafka, and Chroma test project",
    ),
]

PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/99999999/"
CDC_URL = "https://www.cdc.gov/farohealth-fixture"
EVIL_URL = "https://evil.example/x"
PUBMED_MARKER = "FAROHEALTH_PUBMED_MARKER"
WEB_MARKER = "FAROHEALTH_WEB_MARKER"
UPLOAD_MARKER = "FAROHEALTH_UPLOAD_MARKER"
UPLOAD_IDENTITY = "upload-fixture"


class FixtureResearch:
    def __init__(self, hits: list[ResearchHit]) -> None:
        self.hits = hits

    async def search(self, query: str, *, max_results: int) -> list[ResearchHit]:
        del query, max_results
        return list(self.hits)


class FailingResearch:
    async def search(self, query: str, *, max_results: int) -> list[ResearchHit]:
        del query, max_results
        raise ResearchSourceError


async def request_research(backbone: Any, tenant: Any, query: str) -> UUID:
    async with backbone.runtime.transaction() as session:
        response = await backbone._service(session).request_job(
            tenant.organization_id,
            tenant.account_id,
            JobCreateRequest(
                kind=JobKind.RESEARCH_WEB.value,
                conversation_id=tenant.conversation_id,
                parameters={RESEARCH_QUERY_PARAMETER: query},
            ),
            datetime.now(UTC),
        )
    await backbone.relay.drain_once()
    return response.id


async def settle_job(backbone: Any, job_id: UUID) -> dict[str, Any]:
    for _ in range(6):
        row = await backbone.job_row(job_id)
        if row["status"] in {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }:
            return dict(row)
        records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)
        if not records:
            return dict(row)
        try:
            await backbone.consumer.process(records[0])
        except JobAttemptFailedError:
            pass
        await backbone.consumer._consumer.commit()
    return dict(await backbone.job_row(job_id))


async def retrieve(
    backbone: Any,
    *,
    organization_id: UUID,
    conversation_id: UUID,
    query: str,
    job_id: UUID,
    account_id: UUID,
) -> list[Any]:
    async with backbone.runtime.transaction() as session:
        retriever = ConversationRetriever(
            backbone.gateway,
            EvidenceIndex(
                EvidenceChunkRepository(session),
                backbone.chroma_index,
            ),
            backbone.worker_settings,
        )
        return await retriever.retrieve(
            organization_id=organization_id,
            conversation_id=conversation_id,
            query=query,
            job_id=job_id,
            account_id=account_id,
            k=8,
        )


async def identity_count(
    backbone: Any,
    organization_id: UUID,
    conversation_id: UUID,
    source_identity: str,
) -> int:
    async with backbone.runtime.transaction() as session:
        value = (
            await session.execute(
                text(
                    "SELECT count(*) FROM trialscribe.evidence_chunks "
                    "WHERE organization_id = :organization_id "
                    "AND conversation_id = :conversation_id "
                    "AND source_identity = :source_identity"
                ),
                {
                    "organization_id": organization_id,
                    "conversation_id": conversation_id,
                    "source_identity": source_identity,
                },
            )
        ).scalar_one()
    return int(value)


async def seed_upload(backbone: Any, tenant: Any) -> None:
    async with backbone.runtime.transaction() as session:
        evidence = EvidenceIndex(
            EvidenceChunkRepository(session),
            backbone.chroma_index,
        )
        await evidence.put(
            organization_id=tenant.organization_id,
            conversation_id=tenant.conversation_id,
            text=UPLOAD_MARKER,
            vector=fake_vector_for(UPLOAD_MARKER),
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=UPLOAD_IDENTITY,
            start_char=0,
            end_char=len(UPLOAD_MARKER),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )


async def a_fixture_research_is_tenant_scoped(
    backbone: Any,
    tenant: Any,
) -> dict[str, Any]:
    backbone.research_pubmed = FixtureResearch(
        [
            ResearchHit(
                url=PUBMED_URL,
                title="Fixture paper",
                published_on=None,
                body=PUBMED_MARKER,
            )
        ]
    )
    backbone.research_web = FixtureResearch(
        [
            ResearchHit(
                url=CDC_URL,
                title="CDC fixture",
                published_on=None,
                body=WEB_MARKER,
            ),
            ResearchHit(
                url=EVIL_URL,
                title="Evil",
                published_on=None,
                body="should not store",
            ),
        ]
    )
    job_id = await request_research(backbone, tenant, "adult inclusion criteria")
    job = await settle_job(backbone, job_id)
    pubmed_identity = source_identity_for("https://pubmed.ncbi.nlm.nih.gov/99999999")
    cdc_identity = source_identity_for(CDC_URL)
    evil_identity = source_identity_for(EVIL_URL)
    pubmed_found = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=PUBMED_MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    pubmed_again = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=PUBMED_MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    web_found = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=WEB_MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    other_org = await retrieve(
        backbone,
        organization_id=uuid4(),
        conversation_id=tenant.conversation_id,
        query=PUBMED_MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    other_conversation = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=uuid4(),
        query=PUBMED_MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    return {
        "job": job,
        "pubmed_found": pubmed_found,
        "pubmed_again": pubmed_again,
        "web_found": web_found,
        "other_org": other_org,
        "other_conversation": other_conversation,
        "pubmed_identity": pubmed_identity,
        "cdc_identity": cdc_identity,
        "evil_count": await identity_count(
            backbone,
            tenant.organization_id,
            tenant.conversation_id,
            evil_identity,
        ),
    }


async def a_failed_research_leaves_uploads(
    backbone: Any,
    tenant: Any,
) -> dict[str, Any]:
    await seed_upload(backbone, tenant)
    backbone.research_pubmed = FailingResearch()
    backbone.research_web = FailingResearch()
    job_id = await request_research(backbone, tenant, "adult inclusion criteria")
    job = await settle_job(backbone, job_id)
    found = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=UPLOAD_MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    return {"job": job, "found": found}


def test_fixture_research_retrieves_trusted_sources_only() -> None:
    result = asyncio.run(with_backbone(a_fixture_research_is_tenant_scoped))
    assert result["job"]["status"] == JobStatus.SUCCEEDED.value
    pubmed_found = [
        chunk for chunk in result["pubmed_found"] if PUBMED_MARKER in chunk.text
    ]
    pubmed_again = [
        chunk for chunk in result["pubmed_again"] if PUBMED_MARKER in chunk.text
    ]
    web_found = [chunk for chunk in result["web_found"] if WEB_MARKER in chunk.text]
    assert pubmed_found
    assert "Title:" in pubmed_found[0].text
    assert PUBMED_URL.rstrip("/") in pubmed_found[0].text or PUBMED_URL in pubmed_found[0].text
    assert pubmed_found[0].source_kind == EVIDENCE_SOURCE_WEB
    assert pubmed_found[0].source_identity == result["pubmed_identity"]
    assert pubmed_again
    assert PUBMED_MARKER in pubmed_again[0].text
    assert web_found
    assert web_found[0].source_identity == result["cdc_identity"]
    assert result["evil_count"] == 0
    assert result["other_org"] == []
    assert result["other_conversation"] == []


def test_failed_research_does_not_drop_uploaded_evidence() -> None:
    result = asyncio.run(with_backbone(a_failed_research_leaves_uploads))
    assert result["job"]["status"] == JobStatus.FAILED.value
    assert result["found"]
    assert result["found"][0].source_identity == UPLOAD_IDENTITY
    assert result["found"][0].source_kind == EVIDENCE_SOURCE_RESEARCH_DOCUMENT
