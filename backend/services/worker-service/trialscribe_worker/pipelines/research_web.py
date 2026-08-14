"""Search PubMed and allow-listed websites, then store tenant-scoped passages."""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import EmbeddingRequest
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.retrieval.chunking import chunk_text
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.retrieval.research_types import ResearchHit
from trialscribe_worker.retrieval.web_allowlist import (
    canonical_url,
    format_web_passage,
    host_allowed,
    source_identity_for,
)
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    EVIDENCE_SOURCE_WEB,
    MAX_RESEARCH_QUERY_LENGTH,
    RESEARCH_QUERY_PARAMETER,
)
from trialscribe_worker.utils.exceptions import (
    InvalidJobInputError,
    ResearchSourceError,
    WorkerServiceError,
)


def _query(context: JobContext) -> str:
    raw = context.parameters.get(RESEARCH_QUERY_PARAMETER)
    if raw is None:
        raise InvalidJobInputError
    stripped = str(raw).strip()
    if not stripped or len(stripped) > MAX_RESEARCH_QUERY_LENGTH:
        raise InvalidJobInputError
    return stripped


async def _search(
    source: object,
    query: str,
    max_results: int,
) -> tuple[list[ResearchHit], Exception | None]:
    search = getattr(source, "search", None)
    if not callable(search):
        raise WorkerServiceError
    try:
        hits = await search(query, max_results=max_results)
    except Exception as error:
        return [], error
    if not isinstance(hits, list):
        return [], ResearchSourceError()
    return [hit for hit in hits if isinstance(hit, ResearchHit)], None


def _keep(
    pubmed_hits: list[ResearchHit],
    web_hits: list[ResearchHit],
) -> list[tuple[str, str, ResearchHit]]:
    kept: dict[str, tuple[str, ResearchHit]] = {}
    for hit in pubmed_hits:
        url = canonical_url(hit.url)
        if url is None:
            continue
        identity = source_identity_for(url)
        kept.setdefault(identity, (url, hit))
    for hit in web_hits:
        url = canonical_url(hit.url)
        if url is None or not host_allowed(url):
            continue
        identity = source_identity_for(url)
        kept.setdefault(identity, (url, hit))
    return [(identity, url, hit) for identity, (url, hit) in kept.items()]


async def _store_hit(
    context: JobContext,
    gateway: ProviderGateway,
    evidence: EvidenceIndex,
    settings: WorkerSettings,
    conversation_id: UUID,
    identity: str,
    url: str,
    hit: ResearchHit,
    retrieved_on: datetime,
) -> None:
    await evidence.drop_source(
        organization_id=context.organization_id,
        conversation_id=conversation_id,
        source_kind=EVIDENCE_SOURCE_WEB,
        source_identity=identity,
    )
    text = format_web_passage(
        title=hit.title,
        url=url,
        published_on=hit.published_on,
        retrieved_on=retrieved_on.date(),
        body=hit.body,
    )
    chunks = chunk_text(
        text,
        settings.chunk_size_chars,
        settings.chunk_overlap_chars,
    )
    if not chunks:
        return
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    batch_size = settings.embed_batch_size
    for batch_index, start in enumerate(range(0, len(chunks), batch_size)):
        batch = chunks[start : start + batch_size]
        embedded = await gateway.embed(
            EmbeddingRequest(
                texts=[chunk for _start, _end, chunk in batch],
                model=settings.embedding_model,
                organization_id=context.organization_id,
                conversation_id=conversation_id,
                job_id=context.job_id,
                account_id=context.account_id,
                idempotency_key=f"{context.job_id}:{context.attempt}:web:{digest}:{batch_index}",
            )
        )
        for (start_char, end_char, chunk_text_value), vector in zip(
            batch, embedded.vectors, strict=True
        ):
            await evidence.put(
                organization_id=context.organization_id,
                conversation_id=conversation_id,
                text=chunk_text_value,
                vector=vector,
                source_kind=EVIDENCE_SOURCE_WEB,
                source_identity=identity,
                start_char=start_char,
                end_char=end_char,
                embedding_model=embedded.model,
                embedding_dimensions=embedded.dimensions or DEFAULT_EMBEDDING_DIMENSIONS,
            )


async def research_web_pipeline(context: JobContext) -> None:
    """Fetch, filter, and store web passages for one conversation query."""

    if context.gateway is None or context.evidence is None or context.research is None:
        raise WorkerServiceError
    gateway = context.gateway
    evidence = context.evidence
    research = context.research
    if not isinstance(gateway, ProviderGateway) or not isinstance(evidence, EvidenceIndex):
        raise WorkerServiceError
    pubmed = getattr(research, "pubmed", None)
    web = getattr(research, "web", None)
    if pubmed is None or web is None:
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    conversation_id = context.conversation_id
    query = _query(context)
    settings = WorkerSettings()
    await context.check_cancelled()
    await context.report(10)
    pubmed_hits, pubmed_error = await _search(
        pubmed, query, settings.research_max_results
    )
    await context.check_cancelled()
    web_hits, web_error = await _search(web, query, settings.research_max_results)
    kept = _keep(pubmed_hits, web_hits)
    stored = 0
    retrieved_on = datetime.now(UTC)
    total = len(kept)
    for index, (identity, url, hit) in enumerate(kept):
        await context.check_cancelled()
        await _store_hit(
            context,
            gateway,
            evidence,
            settings,
            conversation_id,
            identity,
            url,
            hit,
            retrieved_on,
        )
        stored += 1
        if total:
            await context.report(10 + int(80 * (index + 1) / total))
    if stored == 0 and (pubmed_error is not None or web_error is not None):
        raise ResearchSourceError
    await context.report(100)


async def run_research_web_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
    pubmed: object,
    web: object,
) -> None:
    """Fetch libraries first, then commit each URL in its own transaction."""

    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    context.research = SimpleNamespace(pubmed=pubmed, web=web)
    query = _query(context)
    settings = WorkerSettings()
    await context.check_cancelled()
    await context.report(10)
    pubmed_hits, pubmed_error = await _search(
        pubmed, query, settings.research_max_results
    )
    await context.check_cancelled()
    web_hits, web_error = await _search(web, query, settings.research_max_results)
    kept = _keep(pubmed_hits, web_hits)
    stored = 0
    retrieved_on = datetime.now(UTC)
    total = len(kept)
    gateway = context.gateway
    conversation_id = context.conversation_id
    for index, (identity, url, hit) in enumerate(kept):
        await context.check_cancelled()
        async with runtime.transaction() as session:
            evidence = EvidenceIndex(
                EvidenceChunkRepository(session),
                chroma_index,
            )
            await _store_hit(
                context,
                gateway,
                evidence,
                settings,
                conversation_id,
                identity,
                url,
                hit,
                retrieved_on,
            )
        stored += 1
        if total:
            await context.report(10 + int(80 * (index + 1) / total))
    if stored == 0 and (pubmed_error is not None or web_error is not None):
        raise ResearchSourceError
    await context.report(100)
