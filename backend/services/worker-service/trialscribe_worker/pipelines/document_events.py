"""Turn document lifecycle letters into index jobs or dropped passages."""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_events.contracts.document import DocumentDeleted, DocumentUploaded
from trialscribe_events.envelope import EventEnvelope
from trialscribe_worker.retrieval.chroma_index import EvidenceIndex
from trialscribe_worker.schemas.job import JobCreateRequest
from trialscribe_worker.services.jobs import JobService
from trialscribe_worker.utils.constant import INDEX_DOCUMENT_PARAMETER
from trialscribe_worker.utils.enum import JobKind
from trialscribe_worker.utils.exceptions import WorkerServiceError


async def handle_document_uploaded(
    envelope: EventEnvelope,
    payload: BaseModel,
    session: AsyncSession,
    *,
    jobs: JobService,
) -> None:
    """Queue an index_document job for a file that was just stored."""

    del session
    uploaded = DocumentUploaded.model_validate(payload.model_dump())
    await jobs.request_job(
        uploaded.organization_id,
        uploaded.uploaded_by_account_id,
        JobCreateRequest(
            kind=JobKind.INDEX_DOCUMENT.value,
            conversation_id=uploaded.conversation_id,
            parameters={INDEX_DOCUMENT_PARAMETER: str(uploaded.document_id)},
        ),
        envelope.occurred_at,
    )


async def handle_document_deleted(
    envelope: EventEnvelope,
    payload: BaseModel,
    session: AsyncSession,
    *,
    evidence: EvidenceIndex | None,
) -> None:
    """Remove every passage that belonged to a deleted file."""

    del envelope, session
    if evidence is None:
        raise WorkerServiceError
    deleted = DocumentDeleted.model_validate(payload.model_dump())
    await evidence.drop_source(
        organization_id=deleted.organization_id,
        conversation_id=deleted.conversation_id,
        source_kind=deleted.kind,
        source_identity=str(deleted.document_id),
    )
