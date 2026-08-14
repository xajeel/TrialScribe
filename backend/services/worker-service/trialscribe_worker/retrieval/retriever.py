"""Embed a question and hydrate tenant-scoped passages from the evidence index."""

import hashlib
from uuid import UUID

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.evidence_chunk import EvidenceChunk
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import EmbeddingRequest
from trialscribe_worker.retrieval.chroma_index import EvidenceIndex, require_scope


class ConversationRetriever:
    """Search one conversation's evidence with a natural-language question."""

    def __init__(
        self,
        gateway: ProviderGateway,
        evidence: EvidenceIndex,
        settings: WorkerSettings,
    ) -> None:
        self._gateway = gateway
        self._evidence = evidence
        self._settings = settings

    async def retrieve(
        self,
        *,
        organization_id: UUID | None,
        conversation_id: UUID | None,
        query: str,
        job_id: UUID | None,
        account_id: UUID | None,
        k: int | None = None,
    ) -> list[EvidenceChunk]:
        """Return nearby passages, or nothing for a blank question."""

        organization_id, conversation_id = require_scope(
            organization_id,
            conversation_id,
        )
        stripped = query.strip()
        if not stripped:
            return []
        digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:16]
        key = (
            f"{job_id}:retrieve:{digest}"
            if job_id is not None
            else f"retrieve:{conversation_id}:{digest}"
        )
        embedded = await self._gateway.embed(
            EmbeddingRequest(
                texts=[stripped],
                model=self._settings.embedding_model,
                organization_id=organization_id,
                conversation_id=conversation_id,
                job_id=job_id,
                account_id=account_id,
                idempotency_key=key,
            )
        )
        return await self._evidence.search(
            organization_id=organization_id,
            conversation_id=conversation_id,
            vector=embedded.vectors[0],
            k=k if k is not None else self._settings.retrieve_k,
        )
