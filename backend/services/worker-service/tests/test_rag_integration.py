import asyncio
import importlib.util
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from trialscribe_events.contracts.document import DocumentDeleted
from trialscribe_events.envelope import EventEnvelope
from trialscribe_worker.pipelines.document_events import handle_document_deleted
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.retrieval.chroma_index import EvidenceIndex
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.utils.constant import INDEX_DOCUMENT_PARAMETER
from trialscribe_worker.utils.enum import JobKind, JobStatus
from trialscribe_worker.utils.exceptions import JobAttemptFailedError

_HELPERS = importlib.util.spec_from_file_location(
    "rag_ai_runtime_helpers",
    Path(__file__).with_name("test_ai_runtime_integration.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_runtime = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_runtime)
Backbone = _runtime.Backbone
CONSUME_TIMEOUT_SECONDS = _runtime.CONSUME_TIMEOUT_SECONDS
Tenant = _runtime.Tenant
with_backbone = _runtime.with_backbone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_AI_RUNTIME_INTEGRATION") != "1",
        reason="requires the isolated PostgreSQL, Redis, Kafka, and Chroma test project",
    ),
]

MARKER = "FAROHEALTH_INCLUSION_AGE_18"
BODY = f"{MARKER} is required. Protocol text continues with adult inclusion criteria."


async def seed_document(backbone: Any, tenant: Any) -> UUID:
    document_id = uuid4()
    content = BODY.encode("utf-8")
    async with backbone.runtime.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO trialscribe.documents ("
                "id, conversation_id, organization_id, uploaded_by_account_id, "
                "kind, filename, content_type, byte_size, status, content"
                ") VALUES ("
                ":id, :conversation_id, :organization_id, :account_id, "
                "'research_document', 'notes.txt', 'text/plain', :byte_size, "
                "'pending', :content"
                ")"
            ),
            {
                "id": document_id,
                "conversation_id": tenant.conversation_id,
                "organization_id": tenant.organization_id,
                "account_id": tenant.account_id,
                "byte_size": len(content),
                "content": content,
            },
        )
    return document_id


async def request_index(
    backbone: Any,
    tenant: Any,
    document_id: UUID,
    *,
    hand_over: bool = True,
) -> UUID:
    async with backbone.runtime.transaction() as session:
        response = await backbone._service(session).request_job(
            tenant.organization_id,
            tenant.account_id,
            JobCreateRequest(
                kind=JobKind.INDEX_DOCUMENT.value,
                conversation_id=tenant.conversation_id,
                parameters={INDEX_DOCUMENT_PARAMETER: str(document_id)},
            ),
            datetime.now(UTC),
        )
    if hand_over:
        await backbone.relay.drain_once()
    return response.id


async def process_record(backbone: Any, record: Any) -> None:
    try:
        await backbone.consumer.process(record)
    except JobAttemptFailedError:
        pass


async def document_row(backbone: Any, document_id: UUID) -> dict[str, Any]:
    async with backbone.runtime.transaction() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, error FROM trialscribe.documents WHERE id = :id"
                ),
                {"id": document_id},
            )
        ).mappings().one()
    return dict(row)


async def chunk_count(
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


def _deleted_envelope(tenant: Any, document_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="document.deleted",
        event_version=1,
        occurred_at=datetime.now(UTC),
        organization_id=tenant.organization_id,
        subject=str(document_id),
        correlation_id=uuid4(),
        producer="ai-engine",
        payload={},
    )


async def a_fixture_document_indexes_retrieves_and_deletes(
    backbone: Any,
    tenant: Any,
) -> dict[str, Any]:
    document_id = await seed_document(backbone, tenant)
    identity = str(document_id)
    job_id = await request_index(backbone, tenant, document_id)
    records = await backbone.records(1, CONSUME_TIMEOUT_SECONDS)
    assert len(records) == 1
    await process_record(backbone, records[0])
    await process_record(backbone, records[0])
    await backbone.consumer._consumer.commit()

    row = await document_row(backbone, document_id)
    first_count = await chunk_count(
        backbone,
        tenant.organization_id,
        tenant.conversation_id,
        identity,
    )
    found = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    other_org = await retrieve(
        backbone,
        organization_id=uuid4(),
        conversation_id=tenant.conversation_id,
        query=MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    other_conversation = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=uuid4(),
        query=MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )

    second_job = await request_index(backbone, tenant, document_id)
    await backbone.drain(1, CONSUME_TIMEOUT_SECONDS)
    after_replay = await chunk_count(
        backbone,
        tenant.organization_id,
        tenant.conversation_id,
        identity,
    )
    second_row = await backbone.job_row(second_job)

    async with backbone.runtime.transaction() as session:
        await handle_document_deleted(
            _deleted_envelope(tenant, document_id),
            DocumentDeleted(
                document_id=document_id,
                conversation_id=tenant.conversation_id,
                organization_id=tenant.organization_id,
                kind="research_document",
            ),
            session,
            evidence=EvidenceIndex(
                EvidenceChunkRepository(session),
                backbone.chroma_index,
            ),
        )
    after_delete = await chunk_count(
        backbone,
        tenant.organization_id,
        tenant.conversation_id,
        identity,
    )
    gone = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    return {
        "row": row,
        "found": found,
        "other_org": other_org,
        "other_conversation": other_conversation,
        "first_count": first_count,
        "after_replay": after_replay,
        "second_status": second_row["status"],
        "after_delete": after_delete,
        "gone": gone,
        "identity": identity,
        "job_status": (await backbone.job_row(job_id))["status"],
    }


def test_fixture_retrieval_is_tenant_scoped_and_replaced_on_replay() -> None:
    result = asyncio.run(with_backbone(a_fixture_document_indexes_retrieves_and_deletes))

    assert result["job_status"] == JobStatus.SUCCEEDED.value
    assert result["row"]["status"] == "ready"
    assert result["row"]["error"] is None
    assert result["found"]
    assert MARKER in result["found"][0].text
    assert result["found"][0].source_identity == result["identity"]
    assert result["other_org"] == []
    assert result["other_conversation"] == []
    assert result["first_count"] >= 1
    assert result["after_replay"] == result["first_count"]
    assert result["second_status"] == JobStatus.SUCCEEDED.value
    assert result["after_delete"] == 0
    assert result["gone"] == []
