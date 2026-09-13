"""Search PubMed and allow-listed websites, then store tenant-scoped passages.

One implementation serves both callers. The evidence scope decides whether each
stored source gets its own short database transaction (production) or writes
straight into stores the caller already built (tests).
"""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.config import WorkerSettings, worker_settings
from trialscribe_worker.pipelines.scope import (
    BoundScope,
    EvidenceScope,
    EvidenceTransactionScope,
    evidence_from,
    require_gateway,
)
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import EmbeddingRequest
from trialscribe_worker.retrieval.chunking import chunk_text
from trialscribe_worker.retrieval.chroma_index import (
    ChromaIndex,
    ChunkDraft,
    EvidenceIndex,
)
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

_START_PERCENT = 10
_WORK_PERCENT = 80
_DONE_PERCENT = 100


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


async def _embed_hit(
    context: JobContext,
    gateway: ProviderGateway,
    settings: WorkerSettings,
    conversation_id: UUID,
    identity: str,
    text: str,
) -> list[ChunkDraft]:
    """Chunk one retrieved page and embed it in batches, storing nothing yet."""

    chunks = chunk_text(
        text,
        settings.chunk_size_chars,
        settings.chunk_overlap_chars,
    )
    if not chunks:
        return []
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    batch_size = settings.embed_batch_size
    drafts: list[ChunkDraft] = []
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
                idempotency_key=(
                    f"{context.job_id}:{context.attempt}:web:{digest}:{batch_index}"
                ),
            )
        )
        dimensions = embedded.dimensions or DEFAULT_EMBEDDING_DIMENSIONS
        drafts.extend(
            ChunkDraft(
                text=chunk,
                vector=vector,
                start_char=start_char,
                end_char=end_char,
                embedding_model=embedded.model,
                embedding_dimensions=dimensions,
            )
            for (start_char, end_char, chunk), vector in zip(
                batch, embedded.vectors, strict=True
            )
        )
    return drafts


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
    """Replace one source's passages: embed first, then swap in one batch."""

    drafts = await _embed_hit(
        context,
        gateway,
        settings,
        conversation_id,
        identity,
        format_web_passage(
            title=hit.title,
            url=url,
            published_on=hit.published_on,
            retrieved_on=retrieved_on.date(),
            body=hit.body,
        ),
    )
    if not drafts:
        return
    await evidence.drop_source(
        organization_id=context.organization_id,
        conversation_id=conversation_id,
        source_kind=EVIDENCE_SOURCE_WEB,
        source_identity=identity,
    )
    await evidence.put_many(
        organization_id=context.organization_id,
        conversation_id=conversation_id,
        source_kind=EVIDENCE_SOURCE_WEB,
        source_identity=identity,
        drafts=drafts,
    )


async def research_web_pipeline(
    context: JobContext,
    scope: EvidenceScope | None = None,
) -> None:
    """Fetch, filter, and store web passages for one conversation query."""

    gateway = require_gateway(context)
    pubmed, web = _require_research(context)
    active = scope if scope is not None else BoundScope(evidence_from(context))
    if context.conversation_id is None:
        raise InvalidJobInputError
    conversation_id = context.conversation_id
    query = _query(context)
    settings = worker_settings()

    await context.check_cancelled()
    await context.report(_START_PERCENT)
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
        async with active.open() as evidence:
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
            await context.report(
                _START_PERCENT + int(_WORK_PERCENT * (index + 1) / total)
            )
    if stored == 0 and (pubmed_error is not None or web_error is not None):
        raise ResearchSourceError
    await context.report(_DONE_PERCENT)


async def run_research_web_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
    pubmed: object,
    web: object,
) -> None:
    """Fetch the libraries first, then commit each source in its own transaction."""

    require_gateway(context)
    context.research = SimpleNamespace(pubmed=pubmed, web=web)
    await research_web_pipeline(
        context,
        EvidenceTransactionScope(runtime, chroma_index, context),
    )



def _require_research(context: JobContext) -> tuple[object, object]:
    research = context.research
    if research is None:
        raise WorkerServiceError
    pubmed = getattr(research, "pubmed", None)
    web = getattr(research, "web", None)
    if pubmed is None or web is None:
        raise WorkerServiceError
    return pubmed, web
