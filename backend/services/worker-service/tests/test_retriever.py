import asyncio
import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.providers.fake import FakeChatProvider, FakeEmbeddingProvider, fake_vector_for
from trialscribe_worker.providers.gateway import MemoryUsageRecorder, ProviderGateway
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex, collection_name
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
)
from trialscribe_worker.utils.exceptions import ProviderConfigError

_HELPERS = importlib.util.spec_from_file_location(
    "rag_evidence_index_helpers",
    Path(__file__).with_name("test_evidence_index.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_evidence_helpers = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_evidence_helpers)
CONVERSATION_A = _evidence_helpers.CONVERSATION_A
CONVERSATION_B = _evidence_helpers.CONVERSATION_B
MemoryChroma = _evidence_helpers.MemoryChroma
MemoryChunks = _evidence_helpers.MemoryChunks
ORGANIZATION_A = _evidence_helpers.ORGANIZATION_A
ORGANIZATION_B = _evidence_helpers.ORGANIZATION_B

PHRASE = "FAROHEALTH_INCLUSION_AGE_18"
JOB_ID = UUID("00000000-0000-4000-8000-000000000701")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000702")


async def _no_sleep(_seconds: float) -> None:
    return None


def _retriever(
    embed: FakeEmbeddingProvider | None = None,
) -> tuple[ConversationRetriever, EvidenceIndex, MemoryChroma, FakeEmbeddingProvider]:
    chroma = MemoryChroma()
    evidence = EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(chroma, embed_query=None),
    )
    embed_provider = embed or FakeEmbeddingProvider()
    gateway = ProviderGateway(
        FakeChatProvider(),
        embed_provider,
        WorkerSettings(),
        MemoryUsageRecorder(),
        sleep=_no_sleep,
        rng=lambda: 0.0,
    )
    return (
        ConversationRetriever(gateway, evidence, WorkerSettings()),
        evidence,
        chroma,
        embed_provider,
    )


def test_retrieve_returns_the_matching_phrase_in_the_same_conversation() -> None:
    retriever, evidence, _chroma, _embed = _retriever()
    source_a = str(uuid4())

    async def scenario() -> tuple[list[str], list[str]]:
        await evidence.put(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text=PHRASE,
            vector=fake_vector_for(PHRASE),
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=source_a,
            start_char=0,
            end_char=len(PHRASE),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
        await evidence.put(
            organization_id=ORGANIZATION_B,
            conversation_id=CONVERSATION_B,
            text="other protocol text",
            vector=fake_vector_for("other protocol text"),
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=str(uuid4()),
            start_char=0,
            end_char=19,
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
        found = await retriever.retrieve(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            query=PHRASE,
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=3,
        )
        return [chunk.source_identity for chunk in found], [chunk.text for chunk in found]

    identities, texts = asyncio.run(scenario())
    assert identities == [source_a]
    assert texts == [PHRASE]


def test_retrieve_drops_foreign_ids_even_when_chroma_leaks_them() -> None:
    retriever, evidence, chroma, _embed = _retriever()

    async def scenario() -> tuple[list[UUID], list[UUID]]:
        stored = await evidence.put(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text=PHRASE,
            vector=fake_vector_for(PHRASE),
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=str(uuid4()),
            start_char=0,
            end_char=len(PHRASE),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        )
        chroma.collections[collection_name(CONVERSATION_A)].forced_ids = [
            str(stored.id),
            str(uuid4()),
        ]
        foreign = await retriever.retrieve(
            organization_id=ORGANIZATION_B,
            conversation_id=CONVERSATION_B,
            query=PHRASE,
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=5,
        )
        owned = await retriever.retrieve(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            query=PHRASE,
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
            k=5,
        )
        return [chunk.id for chunk in foreign], [chunk.id for chunk in owned]

    foreign, owned = asyncio.run(scenario())
    assert foreign == []
    assert owned


def test_blank_query_does_not_embed() -> None:
    embed = FakeEmbeddingProvider()
    retriever, _evidence, _chroma, _embed = _retriever(embed)

    found = asyncio.run(
        retriever.retrieve(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            query="   ",
            job_id=JOB_ID,
            account_id=ACCOUNT_ID,
        )
    )

    assert found == []
    assert embed.calls == 0


def test_retrieve_without_organization_is_a_config_error() -> None:
    retriever, _evidence, _chroma, _embed = _retriever()
    try:
        asyncio.run(
            retriever.retrieve(
                organization_id=None,
                conversation_id=CONVERSATION_A,
                query=PHRASE,
                job_id=JOB_ID,
                account_id=ACCOUNT_ID,
            )
        )
    except ProviderConfigError:
        return
    raise AssertionError("retrieve without organization_id must raise ProviderConfigError")
