"""Prove the provider gateway and evidence index with one background job."""

from uuid import UUID

from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import ChatMessage, ChatRequest, EmbeddingRequest
from trialscribe_worker.retrieval.chroma_index import EvidenceIndex
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_PROBE,
)
from trialscribe_worker.utils.exceptions import InvalidJobInputError, WorkerServiceError

PROBE_CHAT_MESSAGE = "ping"
CONVERSATION_ID_PARAMETER = "conversation_id"


def _conversation_id(context: JobContext) -> UUID:
    raw = context.parameters.get(CONVERSATION_ID_PARAMETER)
    if raw is None:
        raise InvalidJobInputError
    try:
        parsed = UUID(str(raw))
    except ValueError:
        raise InvalidJobInputError from None
    if context.conversation_id is not None and parsed != context.conversation_id:
        raise InvalidJobInputError
    return parsed


async def provider_probe_pipeline(context: JobContext) -> None:
    """Chat, embed, store, and search one probe chunk through the worker door."""

    if context.gateway is None or context.evidence is None:
        raise WorkerServiceError
    gateway = context.gateway
    evidence = context.evidence
    if not isinstance(gateway, ProviderGateway) or not isinstance(evidence, EvidenceIndex):
        raise WorkerServiceError

    conversation_id = _conversation_id(context)
    organization_id = context.organization_id
    attempt = context.attempt
    chat_key = f"{context.job_id}:{attempt}:chat:0"
    embed_key = f"{context.job_id}:{attempt}:embed:0"

    await context.check_cancelled()
    chat = await gateway.complete(
        ChatRequest(
            messages=[ChatMessage(role="user", content=PROBE_CHAT_MESSAGE)],
            model=DEFAULT_CHAT_MODEL,
            organization_id=organization_id,
            conversation_id=conversation_id,
            job_id=context.job_id,
            account_id=context.account_id,
            idempotency_key=chat_key,
        )
    )
    await context.report(25)

    await context.check_cancelled()
    text = chat.text or f"echo:{PROBE_CHAT_MESSAGE}"
    embedded = await gateway.embed(
        EmbeddingRequest(
            texts=[text],
            model=DEFAULT_EMBEDDING_MODEL,
            organization_id=organization_id,
            conversation_id=conversation_id,
            job_id=context.job_id,
            account_id=context.account_id,
            idempotency_key=embed_key,
        )
    )
    await context.report(50)

    await context.check_cancelled()
    if not embedded.vectors:
        raise WorkerServiceError
    stored = await evidence.put(
        organization_id=organization_id,
        conversation_id=conversation_id,
        text=text,
        vector=embedded.vectors[0],
        source_kind=EVIDENCE_SOURCE_PROBE,
        source_identity="provider_probe",
        start_char=0,
        end_char=len(text),
        embedding_model=embedded.model,
        embedding_dimensions=embedded.dimensions or DEFAULT_EMBEDDING_DIMENSIONS,
    )
    await context.report(75)

    await context.check_cancelled()
    found = await evidence.search(
        organization_id=organization_id,
        conversation_id=conversation_id,
        vector=embedded.vectors[0],
        k=1,
    )
    matched = [
        row
        for row in found
        if row.id == stored.id
        and row.organization_id == organization_id
        and row.conversation_id == conversation_id
    ]
    if not matched:
        raise WorkerServiceError
    await context.report(100)
