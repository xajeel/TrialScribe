import asyncio
from typing import Any
from uuid import UUID

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.evidence_chunk import EvidenceChunk
from trialscribe_worker.pipelines.provider_probe import provider_probe_pipeline
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider
from trialscribe_worker.providers.gateway import MemoryUsageRecorder, ProviderGateway
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.enum import JobKind
from trialscribe_worker.utils.exceptions import InvalidJobInputError, WorkerServiceError

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000601")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000602")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000603")
JOB_ID = UUID("00000000-0000-4000-8000-000000000604")


class MemoryChunks:
    def __init__(self) -> None:
        self.rows: dict[UUID, EvidenceChunk] = {}

    async def add(self, chunk: EvidenceChunk) -> EvidenceChunk:
        self.rows[chunk.id] = chunk
        return chunk

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        ids: list[UUID],
    ) -> list[EvidenceChunk]:
        matched: list[EvidenceChunk] = []
        for chunk_id in ids:
            row = self.rows.get(chunk_id)
            if (
                row is not None
                and row.organization_id == organization_id
                and row.conversation_id == conversation_id
            ):
                matched.append(row)
        return matched


class MemoryCollection:
    def __init__(self) -> None:
        self.records: dict[str, tuple[list[float], dict[str, str]]] = {}

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str]],
    ) -> None:
        for chunk_id, vector, metadata in zip(ids, embeddings, metadatas, strict=True):
            self.records[chunk_id] = (vector, metadata)

    async def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, object],
    ) -> dict[str, list[list[str]]]:
        del query_embeddings, where
        return {"ids": [list(self.records)[:n_results]]}

    async def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, object] | None = None,
    ) -> None:
        if ids:
            for chunk_id in ids:
                self.records.pop(chunk_id, None)
        if where is not None:
            clauses = where.get("$and")
            if not isinstance(clauses, list):
                return
            stale: list[str] = []
            for chunk_id, (_vector, metadata) in self.records.items():
                matched = True
                for clause in clauses:
                    assert isinstance(clause, dict)
                    key = next(iter(clause))
                    matcher = clause[key]
                    assert isinstance(matcher, dict)
                    if str(metadata.get(key)) != str(matcher["$eq"]):
                        matched = False
                        break
                if matched:
                    stale.append(chunk_id)
            for chunk_id in stale:
                self.records.pop(chunk_id, None)


class MemoryChroma:
    def __init__(self) -> None:
        self.collections: dict[str, MemoryCollection] = {}

    async def get_or_create_collection(self, name: str) -> MemoryCollection:
        if name not in self.collections:
            self.collections[name] = MemoryCollection()
        return self.collections[name]


def build_context(
    *,
    parameters: dict[str, Any] | None = None,
    gateway: ProviderGateway | None = None,
    evidence: EvidenceIndex | None = None,
    reports: list[int] | None = None,
    cancels: list[int] | None = None,
) -> JobContext:
    reported = reports if reports is not None else []
    cancel_at = cancels if cancels is not None else []
    checks = {"count": 0}

    async def report(percent: int) -> None:
        reported.append(percent)

    async def check_cancelled() -> None:
        checks["count"] += 1
        if checks["count"] in cancel_at:
            from trialscribe_worker.utils.exceptions import JobCancelledError

            raise JobCancelledError

    if gateway is None:
        gateway = ProviderGateway(
            FakeChatProvider(),
            FakeEmbeddingProvider(),
            WorkerSettings(),
            MemoryUsageRecorder(),
            rng=lambda: 0.0,
        )
    if evidence is None:
        evidence = EvidenceIndex(
            MemoryChunks(),  # type: ignore[arg-type]
            ChromaIndex(MemoryChroma(), embed_query=None),
        )
    return JobContext(
        job_id=JOB_ID,
        attempt=1,
        parameters=parameters if parameters is not None else {"conversation_id": str(CONVERSATION_ID)},
        report=report,
        check_cancelled=check_cancelled,
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        gateway=gateway,
        evidence=evidence,
    )


def test_provider_probe_kind_is_registered() -> None:
    assert JobKind.PROVIDER_PROBE.value == "provider_probe"


def test_provider_probe_chats_embeds_stores_and_finds() -> None:
    recorder = MemoryUsageRecorder()
    gateway = ProviderGateway(
        FakeChatProvider(),
        FakeEmbeddingProvider(),
        WorkerSettings(),
        recorder,
        rng=lambda: 0.0,
    )
    reports: list[int] = []
    context = build_context(gateway=gateway, reports=reports)
    asyncio.run(provider_probe_pipeline(context))

    assert reports == [25, 50, 75, 100]
    keys = [row.idempotency_key for row in recorder.rows]
    assert f"{JOB_ID}:1:chat:0" in keys
    assert f"{JOB_ID}:1:embed:0" in keys
    chat_row = next(row for row in recorder.rows if row.operation == "chat")
    assert chat_row.cost_micros == 2
    assert chat_row.organization_id == ORGANIZATION_ID
    assert chat_row.conversation_id == CONVERSATION_ID


def test_provider_probe_requires_a_conversation_id() -> None:
    context = build_context(parameters={})
    try:
        asyncio.run(provider_probe_pipeline(context))
    except InvalidJobInputError:
        return
    raise AssertionError("missing conversation_id must raise InvalidJobInputError")


def test_provider_probe_fails_when_the_chunk_does_not_hydrate() -> None:
    class EmptyChunks(MemoryChunks):
        async def get_scoped(
            self,
            organization_id: UUID,
            conversation_id: UUID,
            ids: list[UUID],
        ) -> list[EvidenceChunk]:
            del organization_id, conversation_id, ids
            return []

    evidence = EvidenceIndex(
        EmptyChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )
    context = build_context(evidence=evidence)
    try:
        asyncio.run(provider_probe_pipeline(context))
    except WorkerServiceError:
        return
    raise AssertionError("missing hydrated chunk must fail the job")


def test_provider_probe_honours_cancel_between_steps() -> None:
    from trialscribe_worker.utils.exceptions import JobCancelledError

    context = build_context(cancels=[2])
    try:
        asyncio.run(provider_probe_pipeline(context))
    except JobCancelledError:
        return
    raise AssertionError("cancel between steps must stop the probe")
