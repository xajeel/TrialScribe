"""HTTP routes for reading stored evidence passages."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
)
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_ai.schemas.evidence import EvidenceChunkListResponse, EvidenceChunkResponse
from trialscribe_ai.services.evidence import EvidenceService

router = APIRouter(
    prefix="/conversations/{conversation_id}/evidence-chunks",
    tags=["evidence"],
)

AccountId = Annotated[UUID, Depends(get_current_account_id)]
OrganizationId = Annotated[UUID, Depends(get_current_organization_id)]
Runtime = Annotated[DatabaseRuntime, Depends(get_database_runtime)]


def _service(runtime_session: AsyncSession) -> EvidenceService:
    return EvidenceService(
        ConversationRepository(runtime_session),
        EvidenceChunkRepository(runtime_session),
    )


@router.get("", response_model=EvidenceChunkListResponse)
async def list_evidence_chunks(
    conversation_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    ids: Annotated[list[UUID], Query()] = [],
) -> EvidenceChunkListResponse:
    async with runtime.transaction() as session:
        items = await _service(session).get_many(
            organization_id,
            account_id,
            conversation_id,
            ids,
        )
    return EvidenceChunkListResponse(
        items=[EvidenceChunkResponse.model_validate(item) for item in items]
    )
