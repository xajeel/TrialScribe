"""HTTP routes for durable conversation workspaces."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
)
from trialscribe_ai.repositories.conversation_access import (
    ConversationAccessRepository,
)
from trialscribe_ai.repositories.conversation_messages import (
    ConversationMessageRepository,
)
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.schemas.conversation import (
    ConversationCollaboratorsReplaceRequest,
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessagePageResponse,
    ConversationMessageResponse,
    ConversationPageQuery,
    ConversationPageResponse,
    ConversationRenameRequest,
    ConversationResponse,
    MessagePageQuery,
)
from trialscribe_ai.services.conversations import ConversationRecord, ConversationService
from trialscribe_ai.utils.enum import ConversationStatus

router = APIRouter(prefix="/conversations", tags=["conversations"])

AccountId = Annotated[UUID, Depends(get_current_account_id)]
OrganizationId = Annotated[UUID, Depends(get_current_organization_id)]
Runtime = Annotated[DatabaseRuntime, Depends(get_database_runtime)]
Now = Annotated[datetime, Depends(get_now)]


def _service(runtime_session: AsyncSession) -> ConversationService:
    return ConversationService(
        ConversationRepository(runtime_session),
        ConversationAccessRepository(runtime_session),
        ConversationMessageRepository(runtime_session),
    )


def _conversation_response(record: ConversationRecord) -> ConversationResponse:
    conversation, collaborators = record
    return ConversationResponse(
        id=conversation.id,
        organization_id=conversation.organization_id,
        owner_account_id=conversation.owner_account_id,
        title=conversation.title,
        status=(
            ConversationStatus.ARCHIVED
            if conversation.archived_at is not None
            else ConversationStatus.ACTIVE
        ),
        collaborator_account_ids=collaborators,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_activity_at=conversation.last_activity_at,
        archived_at=conversation.archived_at,
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreateRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> ConversationResponse:
    async with runtime.transaction() as session:
        record = await _service(session).create_conversation(
            organization_id,
            account_id,
            body.title,
            now,
        )
    return _conversation_response(record)


@router.get("", response_model=ConversationPageResponse)
async def list_conversations(
    query: Annotated[ConversationPageQuery, Depends()],
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> ConversationPageResponse:
    async with runtime.transaction() as session:
        records, next_cursor = await _service(session).list_conversations(
            organization_id,
            account_id,
            archived=query.archived,
            cursor=query.cursor,
            limit=query.limit,
        )
    return ConversationPageResponse(
        items=[_conversation_response(record) for record in records],
        next_cursor=next_cursor,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> ConversationResponse:
    async with runtime.transaction() as session:
        record = await _service(session).get_conversation(
            organization_id,
            account_id,
            conversation_id,
        )
    return _conversation_response(record)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    body: ConversationRenameRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> ConversationResponse:
    async with runtime.transaction() as session:
        record = await _service(session).rename_conversation(
            organization_id,
            account_id,
            conversation_id,
            body.title,
        )
    return _conversation_response(record)


@router.delete("/{conversation_id}", response_model=ConversationResponse)
async def archive_conversation(
    conversation_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> ConversationResponse:
    async with runtime.transaction() as session:
        record = await _service(session).archive_conversation(
            organization_id,
            account_id,
            conversation_id,
            now,
        )
    return _conversation_response(record)


@router.post("/{conversation_id}/restore", response_model=ConversationResponse)
async def restore_conversation(
    conversation_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> ConversationResponse:
    async with runtime.transaction() as session:
        record = await _service(session).restore_conversation(
            organization_id,
            account_id,
            conversation_id,
        )
    return _conversation_response(record)


@router.put("/{conversation_id}/collaborators", response_model=ConversationResponse)
async def replace_collaborators(
    conversation_id: UUID,
    body: ConversationCollaboratorsReplaceRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> ConversationResponse:
    async with runtime.transaction() as session:
        record = await _service(session).replace_collaborators(
            organization_id,
            account_id,
            conversation_id,
            body.account_ids,
        )
    return _conversation_response(record)


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def append_message(
    conversation_id: UUID,
    body: ConversationMessageCreateRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> ConversationMessageResponse:
    async with runtime.transaction() as session:
        message = await _service(session).append_user_message(
            organization_id,
            account_id,
            conversation_id,
            body.content,
            now,
        )
    return ConversationMessageResponse.model_validate(message)


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessagePageResponse,
)
async def list_messages(
    conversation_id: UUID,
    query: Annotated[MessagePageQuery, Depends()],
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> ConversationMessagePageResponse:
    async with runtime.transaction() as session:
        messages, next_cursor = await _service(session).list_messages(
            organization_id,
            account_id,
            conversation_id,
            cursor=query.cursor,
            limit=query.limit,
        )
    return ConversationMessagePageResponse(
        items=[
            ConversationMessageResponse.model_validate(message) for message in messages
        ],
        next_cursor=next_cursor,
    )
