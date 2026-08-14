import asyncio
import importlib.util
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from trialscribe_worker.providers.fake import fake_vector_for
from trialscribe_worker.providers.types import ChatRequest, ChatResult
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.m11_sections import M11SectionStore
from trialscribe_worker.retrieval.chroma_index import EvidenceIndex
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_TRIAL_DATA,
    GENERATE_EXPECTED_REVISIONS_PARAMETER,
    GENERATE_SECTIONS_PARAMETER,
)
from trialscribe_worker.utils.enum import JobKind, JobStatus
from trialscribe_worker.utils.exceptions import (
    JobAttemptFailedError,
    ProviderUnavailableError,
)

_HELPERS = importlib.util.spec_from_file_location(
    "generate_sections_runtime_helpers",
    Path(__file__).with_name("test_ai_runtime_integration.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_runtime = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_runtime)
CONSUME_TIMEOUT_SECONDS = _runtime.CONSUME_TIMEOUT_SECONDS
with_backbone = _runtime.with_backbone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_AI_RUNTIME_INTEGRATION") != "1",
        reason="requires the isolated PostgreSQL, Redis, Kafka, and Chroma test project",
    ),
]

MARKER = "FAROHEALTH_INCLUSION_AGE_18"
CATALOG_VERSION = "ICH_M11_STEP_4_2025_11_19"
_ID_IN_PROMPT = re.compile(
    r"id=([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


class CitingChat:
    """Cite the first evidence id in the prompt; optionally fail one section."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on

    async def complete(self, request: ChatRequest) -> ChatResult:
        combined = "\n".join(message.content for message in request.messages)
        for number in ("4", "5"):
            if f"number={number}" in combined and self.fail_on == number:
                raise ProviderUnavailableError()
        match = _ID_IN_PROMPT.search(combined)
        cite = f"[cite:{match.group(1)}]" if match else ""
        return ChatResult(
            text=f"Inclusion requires {MARKER} {cite}".strip(),
            model="fake-chat",
            input_tokens=10,
            output_tokens=5,
            cache_hit_tokens=0,
            latency_ms=1,
        )


async def request_generate(
    backbone: Any,
    tenant: Any,
    section_numbers: list[str],
    expected_revisions: dict[str, int],
) -> UUID:
    async with backbone.runtime.transaction() as session:
        response = await backbone._service(session).request_job(
            tenant.organization_id,
            tenant.account_id,
            JobCreateRequest(
                kind=JobKind.GENERATE_SECTIONS.value,
                conversation_id=tenant.conversation_id,
                parameters={
                    GENERATE_SECTIONS_PARAMETER: section_numbers,
                    GENERATE_EXPECTED_REVISIONS_PARAMETER: expected_revisions,
                },
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


async def seed_section(
    backbone: Any,
    tenant: Any,
    *,
    number: str,
    title: str,
    position: int,
) -> None:
    async with backbone.runtime.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO trialscribe.m11_sections ("
                "id, conversation_id, organization_id, catalog_version, "
                "section_number, title, position, instructions, content, "
                "status, current_revision"
                ") VALUES ("
                ":id, :conversation_id, :organization_id, :catalog_version, "
                ":section_number, :title, :position, '', '', 'draft', 0"
                ")"
            ),
            {
                "id": uuid4(),
                "conversation_id": tenant.conversation_id,
                "organization_id": tenant.organization_id,
                "catalog_version": CATALOG_VERSION,
                "section_number": number,
                "title": title,
                "position": position,
            },
        )


async def seed_trial(backbone: Any, tenant: Any) -> UUID:
    async with backbone.runtime.transaction() as session:
        evidence = EvidenceIndex(
            EvidenceChunkRepository(session),
            backbone.chroma_index,
        )
        chunk = await evidence.put(
            organization_id=tenant.organization_id,
            conversation_id=tenant.conversation_id,
            text=MARKER,
            vector=fake_vector_for(MARKER),
            source_kind=EVIDENCE_SOURCE_TRIAL_DATA,
            source_identity="trial-fixture",
            start_char=0,
            end_char=len(MARKER),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
    return chunk.id


async def load_section(
    backbone: Any,
    organization_id: UUID,
    conversation_id: UUID,
    section_number: str,
) -> Any:
    async with backbone.runtime.transaction() as session:
        return await M11SectionStore(session).get_scoped(
            organization_id,
            conversation_id,
            section_number,
        )


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


async def a_fixture_section_is_cited_and_isolated(
    backbone: Any,
    tenant: Any,
) -> dict[str, Any]:
    await seed_section(
        backbone,
        tenant,
        number="5",
        title="TRIAL POPULATION",
        position=5,
    )
    chunk_id = await seed_trial(backbone, tenant)
    job_id = await request_generate(backbone, tenant, ["5"], {"5": 0})
    job = await settle_job(backbone, job_id)
    section = await load_section(
        backbone,
        tenant.organization_id,
        tenant.conversation_id,
        "5",
    )
    found = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=tenant.conversation_id,
        query=MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    other_conversation = await load_section(
        backbone,
        tenant.organization_id,
        uuid4(),
        "5",
    )
    other_retrieve = await retrieve(
        backbone,
        organization_id=tenant.organization_id,
        conversation_id=uuid4(),
        query=MARKER,
        job_id=job_id,
        account_id=tenant.account_id,
    )
    return {
        "job": job,
        "section": section,
        "chunk_id": chunk_id,
        "found": found,
        "other_conversation": other_conversation,
        "other_retrieve": other_retrieve,
    }


async def a_failed_neighbour_keeps_the_saved_draft(
    backbone: Any,
    tenant: Any,
) -> dict[str, Any]:
    await seed_section(
        backbone,
        tenant,
        number="5",
        title="TRIAL POPULATION",
        position=5,
    )
    await seed_section(
        backbone,
        tenant,
        number="4",
        title="TRIAL DESIGN",
        position=4,
    )
    await seed_trial(backbone, tenant)
    job_id = await request_generate(
        backbone,
        tenant,
        ["5", "4"],
        {"5": 0, "4": 0},
    )
    job = await settle_job(backbone, job_id)
    section_five = await load_section(
        backbone,
        tenant.organization_id,
        tenant.conversation_id,
        "5",
    )
    section_four = await load_section(
        backbone,
        tenant.organization_id,
        tenant.conversation_id,
        "4",
    )
    return {"job": job, "section_five": section_five, "section_four": section_four}


def test_fixture_generation_stores_a_resolving_citation() -> None:
    result = asyncio.run(
        with_backbone(a_fixture_section_is_cited_and_isolated, chat=CitingChat())
    )
    assert result["job"]["status"] == JobStatus.SUCCEEDED.value
    section = result["section"]
    assert section is not None
    assert section.current_revision == 1
    assert MARKER in section.content
    assert f"[cite:{result['chunk_id']}]" in section.content
    found = [chunk for chunk in result["found"] if chunk.id == result["chunk_id"]]
    assert found
    assert MARKER in found[0].text
    assert result["other_conversation"] is None
    assert result["other_retrieve"] == []


def test_failed_neighbour_does_not_rewrite_the_saved_section() -> None:
    result = asyncio.run(
        with_backbone(
            a_failed_neighbour_keeps_the_saved_draft,
            chat=CitingChat(fail_on="4"),
        )
    )
    assert result["job"]["status"] == JobStatus.FAILED.value
    five = result["section_five"]
    four = result["section_four"]
    assert five is not None
    assert MARKER in five.content
    assert five.current_revision == 1
    assert four is not None
    assert four.content == ""
    assert four.current_revision == 0
