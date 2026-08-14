"""Index one uploaded conversation file into tenant-scoped evidence chunks."""

from uuid import UUID

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.source_document import SourceDocument
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import EmbeddingRequest
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.source_documents import SourceDocumentRepository
from trialscribe_worker.retrieval.chunking import chunk_text, page_for_span
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.retrieval.extraction import extract_source
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    INDEX_DOCUMENT_PARAMETER,
    INDEX_EMPTY_TEXT_ERROR,
    INDEX_EXTRACTION_FAILED_ERROR,
    INDEX_FAILED_ERROR,
)
from trialscribe_worker.utils.exceptions import (
    DocumentExtractionError,
    InvalidJobInputError,
    JobCancelledError,
    WorkerServiceError,
)

READY_STATUS = "ready"
FAILED_STATUS = "failed"


def _document_id(context: JobContext) -> UUID:
    raw = context.parameters.get(INDEX_DOCUMENT_PARAMETER)
    if raw is None:
        raise InvalidJobInputError
    try:
        parsed = UUID(str(raw))
    except ValueError:
        raise InvalidJobInputError from None
    return parsed


async def index_document_pipeline(context: JobContext) -> None:
    """Extract, chunk, embed, and replace passages for one uploaded file."""

    if context.gateway is None or context.evidence is None or context.sources is None:
        raise WorkerServiceError
    gateway = context.gateway
    evidence = context.evidence
    sources = context.sources
    if not isinstance(gateway, ProviderGateway) or not isinstance(evidence, EvidenceIndex):
        raise WorkerServiceError
    if not isinstance(sources, SourceDocumentRepository) and not hasattr(
        sources, "get_scoped"
    ):
        raise WorkerServiceError

    if context.conversation_id is None:
        raise InvalidJobInputError
    document_id = _document_id(context)
    settings = WorkerSettings()

    try:
        await _index(
            context,
            gateway,
            evidence,
            sources,
            settings,
            document_id,
            context.conversation_id,
        )
    except (InvalidJobInputError, JobCancelledError):
        raise
    except Exception:
        if context.attempt >= context.max_attempts:
            await sources.mark_status(
                context.organization_id,
                context.conversation_id,
                document_id,
                FAILED_STATUS,
                INDEX_FAILED_ERROR,
            )
        raise


async def _index(
    context: JobContext,
    gateway: ProviderGateway,
    evidence: EvidenceIndex,
    sources: object,
    settings: WorkerSettings,
    document_id: UUID,
    conversation_id: UUID,
) -> None:
    await context.check_cancelled()
    document = await sources.get_scoped(  # type: ignore[union-attr]
        context.organization_id,
        conversation_id,
        document_id,
    )
    if document is None:
        raise InvalidJobInputError
    if not isinstance(document, SourceDocument):
        raise WorkerServiceError

    try:
        extracted = extract_source(document.kind, document.content_type, document.content)
    except DocumentExtractionError:
        await sources.mark_status(  # type: ignore[union-attr]
            context.organization_id,
            conversation_id,
            document_id,
            FAILED_STATUS,
            INDEX_EXTRACTION_FAILED_ERROR,
        )
        return

    if not extracted.text.strip():
        await sources.mark_status(  # type: ignore[union-attr]
            context.organization_id,
            conversation_id,
            document_id,
            FAILED_STATUS,
            INDEX_EMPTY_TEXT_ERROR,
        )
        return
    chunks = chunk_text(
        extracted.text,
        settings.chunk_size_chars,
        settings.chunk_overlap_chars,
    )
    if not chunks:
        await sources.mark_status(  # type: ignore[union-attr]
            context.organization_id,
            conversation_id,
            document_id,
            FAILED_STATUS,
            INDEX_EMPTY_TEXT_ERROR,
        )
        return

    await context.report(20)
    await evidence.drop_source(
        organization_id=context.organization_id,
        conversation_id=conversation_id,
        source_kind=document.kind,
        source_identity=str(document.id),
    )

    total = len(chunks)
    done = 0
    batch_size = settings.embed_batch_size
    for batch_index, start in enumerate(range(0, total, batch_size)):
        await context.check_cancelled()
        batch = chunks[start : start + batch_size]
        embedded = await gateway.embed(
            EmbeddingRequest(
                texts=[text for _start, _end, text in batch],
                model=settings.embedding_model,
                organization_id=context.organization_id,
                conversation_id=conversation_id,
                job_id=context.job_id,
                account_id=context.account_id,
                idempotency_key=f"{context.job_id}:{context.attempt}:embed:{batch_index}",
            )
        )
        for (start_char, end_char, text), vector in zip(
            batch, embedded.vectors, strict=True
        ):
            await evidence.put(
                organization_id=context.organization_id,
                conversation_id=conversation_id,
                text=text,
                vector=vector,
                source_kind=document.kind,
                source_identity=str(document.id),
                start_char=start_char,
                end_char=end_char,
                embedding_model=embedded.model,
                embedding_dimensions=embedded.dimensions or DEFAULT_EMBEDDING_DIMENSIONS,
                page_number=page_for_span(extracted.pages, start_char, end_char),
            )
        done += len(batch)
        await context.report(20 + int(70 * done / total))

    await sources.mark_status(  # type: ignore[union-attr]
        context.organization_id,
        conversation_id,
        document_id,
        READY_STATUS,
        None,
    )
    await context.report(100)


async def run_index_document_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
) -> None:
    """Index inside one transaction; persist a last-attempt failure in another.

    Chroma writes leave this function as soon as they happen. PostgreSQL writes
    do not. If the work raises, the SQL transaction rolls back, so the failed
    document status has to be written again after that rollback or the file
    stays `pending` forever.
    """

    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    try:
        async with runtime.transaction() as session:
            context.evidence = EvidenceIndex(
                EvidenceChunkRepository(session),
                chroma_index,
            )
            context.sources = SourceDocumentRepository(session)
            await index_document_pipeline(context)
    except (InvalidJobInputError, JobCancelledError):
        raise
    except Exception:
        await _commit_terminal_failure(context, runtime)
        raise


async def _commit_terminal_failure(
    context: JobContext,
    runtime: DatabaseRuntime,
) -> None:
    if context.attempt < context.max_attempts or context.conversation_id is None:
        return
    try:
        document_id = _document_id(context)
    except InvalidJobInputError:
        return
    try:
        async with runtime.transaction() as session:
            await SourceDocumentRepository(session).mark_status(
                context.organization_id,
                context.conversation_id,
                document_id,
                FAILED_STATUS,
                INDEX_FAILED_ERROR,
            )
    except Exception:
        return
