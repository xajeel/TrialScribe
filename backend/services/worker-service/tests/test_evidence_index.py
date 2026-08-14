import asyncio
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects import postgresql

from trialscribe_worker.models.evidence_chunk import EvidenceChunk
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.retrieval.chroma_index import (
    ChromaIndex,
    EvidenceIndex,
    collection_name,
)
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_ORGANIZATION_CONVERSATION_INDEX,
    EVIDENCE_SOURCE_PROBE,
    EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
)
from trialscribe_worker.utils.exceptions import ProviderConfigError

ORGANIZATION_A = UUID("00000000-0000-4000-8000-000000000501")
ORGANIZATION_B = UUID("00000000-0000-4000-8000-000000000502")
CONVERSATION_A = UUID("00000000-0000-4000-8000-000000000503")
CONVERSATION_B = UUID("00000000-0000-4000-8000-000000000504")
PROBE_VECTOR = [0.1] * DEFAULT_EMBEDDING_DIMENSIONS


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

    async def list_ids_for_source(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        source_kind: str,
        source_identity: str,
    ) -> list[UUID]:
        return [
            chunk.id
            for chunk in self.rows.values()
            if chunk.organization_id == organization_id
            and chunk.conversation_id == conversation_id
            and chunk.source_kind == source_kind
            and chunk.source_identity == source_identity
        ]

    async def delete_for_source(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        source_kind: str,
        source_identity: str,
    ) -> None:
        stale = await self.list_ids_for_source(
            organization_id,
            conversation_id,
            source_kind,
            source_identity,
        )
        for chunk_id in stale:
            self.rows.pop(chunk_id, None)


def _clause_value(clause: dict[str, object]) -> tuple[str, str]:
    key = next(iter(clause))
    matcher = clause[key]
    assert isinstance(matcher, dict)
    return key, str(matcher["$eq"])


def _metadata_matches(metadata: dict[str, object], where: dict[str, object]) -> bool:
    clauses = where.get("$and")
    if not isinstance(clauses, list):
        return False
    for clause in clauses:
        assert isinstance(clause, dict)
        key, expected = _clause_value(clause)
        if str(metadata.get(key)) != expected:
            return False
    return True


class MemoryCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.records: dict[str, tuple[list[float], dict[str, str]]] = {}
        self.last_where: dict[str, object] | None = None
        self.forced_ids: list[str] | None = None

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
        del query_embeddings
        self.last_where = where
        if self.forced_ids is not None:
            return {"ids": [self.forced_ids[:n_results]]}
        organization_id, conversation_id = _where_ids(where)
        matched = [
            chunk_id
            for chunk_id, (_vector, metadata) in self.records.items()
            if metadata.get("organization_id") == organization_id
            and metadata.get("conversation_id") == conversation_id
        ]
        return {"ids": [matched[:n_results]]}

    async def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, object] | None = None,
    ) -> None:
        if ids:
            for chunk_id in ids:
                self.records.pop(chunk_id, None)
        if where is not None:
            stale = [
                chunk_id
                for chunk_id, (_vector, metadata) in self.records.items()
                if _metadata_matches(metadata, where)
            ]
            for chunk_id in stale:
                self.records.pop(chunk_id, None)


class MemoryChroma:
    def __init__(self) -> None:
        self.collections: dict[str, MemoryCollection] = {}

    async def get_or_create_collection(self, name: str) -> MemoryCollection:
        if name not in self.collections:
            self.collections[name] = MemoryCollection(name)
        return self.collections[name]


def _where_ids(where: dict[str, object]) -> tuple[str, str]:
    clauses = where["$and"]
    assert isinstance(clauses, list)
    organization = clauses[0]["organization_id"]["$eq"]
    conversation = clauses[1]["conversation_id"]["$eq"]
    return str(organization), str(conversation)


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        raise _Captured


class _Captured(Exception):
    pass


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def make_index(client: MemoryChroma | None = None) -> tuple[EvidenceIndex, MemoryChroma]:
    chroma_client = client or MemoryChroma()
    index = EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(chroma_client, embed_query=None),
    )
    return index, chroma_client


async def put_chunk(
    index: EvidenceIndex,
    *,
    organization_id: UUID,
    conversation_id: UUID,
    text: str,
    source_identity: str = "provider_probe",
    source_kind: str = EVIDENCE_SOURCE_PROBE,
) -> EvidenceChunk:
    return await index.put(
        organization_id=organization_id,
        conversation_id=conversation_id,
        text=text,
        vector=PROBE_VECTOR,
        source_kind=source_kind,
        source_identity=source_identity,
        start_char=0,
        end_char=len(text),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
    )


def test_collection_name_is_c_plus_conversation_hex() -> None:
    assert collection_name(CONVERSATION_A) == f"c{CONVERSATION_A.hex}"


def test_put_uses_the_conversation_collection() -> None:
    index, client = make_index()
    asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text="alpha",
        )
    )
    assert list(client.collections) == [collection_name(CONVERSATION_A)]


def test_search_drops_ids_that_do_not_hydrate_in_scope() -> None:
    index, client = make_index()
    chunk_a = asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text="alpha",
        )
    )
    chunk_b = asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_B,
            conversation_id=CONVERSATION_B,
            text="beta",
        )
    )
    leaked = client.collections[collection_name(CONVERSATION_A)]
    leaked.forced_ids = [str(chunk_a.id), str(chunk_b.id)]

    found = asyncio.run(
        index.search(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            vector=PROBE_VECTOR,
            k=5,
        )
    )

    assert [chunk.id for chunk in found] == [chunk_a.id]
    assert leaked.last_where is not None
    organization, conversation = _where_ids(leaked.last_where)
    assert organization == str(ORGANIZATION_A)
    assert conversation == str(CONVERSATION_A)


def test_search_without_organization_id_is_a_config_error() -> None:
    index, _client = make_index()
    try:
        asyncio.run(
            index.search(
                organization_id=None,
                conversation_id=CONVERSATION_A,
                vector=PROBE_VECTOR,
                k=1,
            )
        )
    except ProviderConfigError:
        return
    raise AssertionError("search without organization_id must raise ProviderConfigError")


def test_the_model_declares_no_foreign_key_it_cannot_resolve() -> None:
    declared = [
        column.name for column in EvidenceChunk.__table__.columns if column.foreign_keys
    ]
    assert declared == []
    indexes = {index.name: index for index in EvidenceChunk.__table__.indexes}
    listing = indexes[EVIDENCE_ORGANIZATION_CONVERSATION_INDEX]
    assert [column.name for column in listing.columns] == [
        "organization_id",
        "conversation_id",
        "id",
    ]


def test_get_scoped_sql_names_both_tenant_columns() -> None:
    session = RecordingSession()
    repository = EvidenceChunkRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            repository.get_scoped(ORGANIZATION_A, CONVERSATION_A, [uuid4()])
        )
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "organization_id" in sql
    assert "conversation_id" in sql
    assert "evidence_chunks" in sql


def test_drop_source_removes_only_that_source() -> None:
    index, client = make_index()
    source_a = str(uuid4())
    source_b = str(uuid4())
    chunk_a = asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text="alpha",
            source_identity=source_a,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
        )
    )
    chunk_b = asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text="beta",
            source_identity=source_b,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
        )
    )

    asyncio.run(
        index.drop_source(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=source_a,
        )
    )

    collection = client.collections[collection_name(CONVERSATION_A)]
    assert str(chunk_a.id) not in collection.records
    assert str(chunk_b.id) in collection.records
    collection.forced_ids = [str(chunk_a.id), str(chunk_b.id)]
    found = asyncio.run(
        index.search(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            vector=PROBE_VECTOR,
            k=5,
        )
    )
    assert [chunk.id for chunk in found] == [chunk_b.id]


def test_drop_source_removes_chroma_orphans_when_postgres_has_no_ids() -> None:
    chunks = MemoryChunks()
    client = MemoryChroma()
    index = EvidenceIndex(
        chunks,  # type: ignore[arg-type]
        ChromaIndex(client, embed_query=None),
    )
    source = str(uuid4())
    chunk = asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text="orphan",
            source_identity=source,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
        )
    )
    chunks.rows.clear()
    collection = client.collections[collection_name(CONVERSATION_A)]
    assert str(chunk.id) in collection.records

    asyncio.run(
        index.drop_source(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
            source_identity=source,
        )
    )
    assert str(chunk.id) not in collection.records

    replacement = asyncio.run(
        put_chunk(
            index,
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            text="kept",
            source_identity=source,
            source_kind=EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
        )
    )
    collection.forced_ids = [str(chunk.id), str(replacement.id)]
    found = asyncio.run(
        index.search(
            organization_id=ORGANIZATION_A,
            conversation_id=CONVERSATION_A,
            vector=PROBE_VECTOR,
            k=5,
        )
    )
    assert [row.id for row in found] == [replacement.id]


def test_list_and_delete_for_source_sql_names_tenant_and_source() -> None:
    session = RecordingSession()
    repository = EvidenceChunkRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(
            repository.list_ids_for_source(
                ORGANIZATION_A,
                CONVERSATION_A,
                EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
                "source-a",
            )
        )
    except _Captured:
        pass
    listed = compiled(session.statements[0])
    assert "organization_id" in listed
    assert "conversation_id" in listed
    assert "source_kind" in listed
    assert "source_identity" in listed

    try:
        asyncio.run(
            repository.delete_for_source(
                ORGANIZATION_A,
                CONVERSATION_A,
                EVIDENCE_SOURCE_RESEARCH_DOCUMENT,
                "source-a",
            )
        )
    except _Captured:
        pass
    deleted = compiled(session.statements[1])
    assert "DELETE" in deleted.upper()
    assert "organization_id" in deleted
    assert "conversation_id" in deleted
    assert "source_identity" in deleted

