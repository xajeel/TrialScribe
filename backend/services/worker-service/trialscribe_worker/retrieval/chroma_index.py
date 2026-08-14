"""Chroma collections named for a conversation, hydrated from PostgreSQL."""

from typing import Protocol
from uuid import UUID, uuid4

from trialscribe_worker.models.evidence_chunk import EvidenceChunk
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.utils.exceptions import ProviderConfigError


class ChromaCollection(Protocol):
    """The collection methods the evidence index needs."""

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str]],
    ) -> object: ...

    async def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, object],
    ) -> object: ...

    async def delete(self, ids: list[str]) -> object: ...


class ChromaClient(Protocol):
    """The client methods the evidence index needs."""

    async def get_or_create_collection(self, name: str) -> ChromaCollection: ...


def collection_name(conversation_id: UUID) -> str:
    """Return the Chroma collection bound to one conversation."""

    return f"c{conversation_id.hex}"


def require_scope(
    organization_id: UUID | None,
    conversation_id: UUID | None,
) -> tuple[UUID, UUID]:
    """Refuse a vector operation that is missing either tenant key."""

    if organization_id is None or conversation_id is None:
        raise ProviderConfigError(
            "evidence query requires organization and conversation scope"
        )
    return organization_id, conversation_id


def tenant_where(organization_id: UUID, conversation_id: UUID) -> dict[str, object]:
    """Return a Chroma where-clause that names both tenant keys."""

    return {
        "$and": [
            {"organization_id": {"$eq": str(organization_id)}},
            {"conversation_id": {"$eq": str(conversation_id)}},
        ]
    }


async def _collection_size(collection: object) -> int | None:
    """Return how many vectors a collection holds, when the client can say."""

    count = getattr(collection, "count", None)
    if not callable(count):
        return None
    value = count()
    if hasattr(value, "__await__"):
        value = await value
    return int(value)


def _ids_from_query(result: object) -> list[str]:
    raw = result["ids"] if isinstance(result, dict) else getattr(result, "ids", None)
    if not raw:
        return []
    first = raw[0]
    return [str(item) for item in first]


class ChromaIndex:
    """Upsert and query vectors in a per-conversation collection."""

    def __init__(self, client: ChromaClient, embed_query: object) -> None:
        self._client = client
        self._embed_query = embed_query

    async def upsert(
        self,
        chunk_id: UUID,
        vector: list[float],
        organization_id: UUID | None,
        conversation_id: UUID | None,
    ) -> None:
        """Write one vector and both tenant ids into that conversation's collection."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        collection = await self._client.get_or_create_collection(
            collection_name(conversation_id)
        )
        await collection.upsert(
            ids=[str(chunk_id)],
            embeddings=[vector],
            metadatas=[
                {
                    "organization_id": str(organization_id),
                    "conversation_id": str(conversation_id),
                }
            ],
        )

    async def query(
        self,
        organization_id: UUID | None,
        conversation_id: UUID | None,
        vector: list[float],
        k: int,
    ) -> list[UUID]:
        """Return nearby chunk ids, always filtered by both tenant keys."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        collection = await self._client.get_or_create_collection(
            collection_name(conversation_id)
        )
        counted = await _collection_size(collection)
        if counted == 0:
            return []
        result = await collection.query(
            query_embeddings=[vector],
            n_results=min(k, counted) if counted is not None else k,
            where=tenant_where(organization_id, conversation_id),
        )
        found: list[UUID] = []
        for raw_id in _ids_from_query(result):
            try:
                found.append(UUID(raw_id))
            except ValueError:
                continue
        return found

    async def delete(
        self,
        organization_id: UUID | None,
        conversation_id: UUID | None,
        ids: list[UUID],
    ) -> None:
        """Remove vectors by id from the conversation collection."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        if not ids:
            return
        collection = await self._client.get_or_create_collection(
            collection_name(conversation_id)
        )
        await collection.delete(ids=[str(chunk_id) for chunk_id in ids])


class EvidenceIndex:
    """PostgreSQL holds the passage; Chroma holds only the vector and chunk id."""

    def __init__(self, chunks: EvidenceChunkRepository, chroma: ChromaIndex) -> None:
        self._chunks = chunks
        self._chroma = chroma

    async def put(
        self,
        *,
        organization_id: UUID | None,
        conversation_id: UUID | None,
        text: str,
        vector: list[float],
        source_kind: str,
        source_identity: str,
        start_char: int,
        end_char: int,
        embedding_model: str,
        embedding_dimensions: int,
        page_number: int | None = None,
    ) -> EvidenceChunk:
        """Write the passage, then upsert its vector into the conversation collection."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        chunk = EvidenceChunk(
            id=uuid4(),
            organization_id=organization_id,
            conversation_id=conversation_id,
            source_kind=source_kind,
            source_identity=source_identity,
            page_number=page_number,
            start_char=start_char,
            end_char=end_char,
            text=text,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )
        stored = await self._chunks.add(chunk)
        await self._chroma.upsert(
            stored.id,
            vector,
            organization_id,
            conversation_id,
        )
        return stored

    async def search(
        self,
        *,
        organization_id: UUID | None,
        conversation_id: UUID | None,
        vector: list[float],
        k: int,
    ) -> list[EvidenceChunk]:
        """Query Chroma, then keep only rows PostgreSQL still owns in this scope."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        ids = await self._chroma.query(organization_id, conversation_id, vector, k)
        return await self._chunks.get_scoped(organization_id, conversation_id, ids)

    async def drop_source(
        self,
        *,
        organization_id: UUID | None,
        conversation_id: UUID | None,
        source_kind: str,
        source_identity: str,
    ) -> None:
        """Remove one source's passages from PostgreSQL and Chroma."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        ids = await self._chunks.list_ids_for_source(
            organization_id,
            conversation_id,
            source_kind,
            source_identity,
        )
        if ids:
            await self._chroma.delete(organization_id, conversation_id, ids)
        await self._chunks.delete_for_source(
            organization_id,
            conversation_id,
            source_kind,
            source_identity,
        )
