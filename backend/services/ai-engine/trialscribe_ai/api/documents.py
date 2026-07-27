"""HTTP routes for conversation document ingestion."""

from datetime import datetime
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
)
from trialscribe_ai.config.settings import DOCUMENT_MAX_SIZE_BYTES
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.repositories.documents import DocumentRepository
from trialscribe_ai.schemas.document import (
    DocumentPageQuery,
    DocumentPageResponse,
    DocumentResponse,
)
from trialscribe_ai.services.documents import DocumentService
from trialscribe_ai.utils.enum import DocumentKind

router = APIRouter(
    prefix="/conversations/{conversation_id}/documents",
    tags=["documents"],
)

AccountId = Annotated[UUID, Depends(get_current_account_id)]
OrganizationId = Annotated[UUID, Depends(get_current_organization_id)]
Runtime = Annotated[DatabaseRuntime, Depends(get_database_runtime)]
Now = Annotated[datetime, Depends(get_now)]


def _service(runtime_session: AsyncSession) -> DocumentService:
    return DocumentService(
        ConversationRepository(runtime_session),
        DocumentRepository(runtime_session),
    )


def _content_disposition(filename: str) -> str:
    sanitized = "".join(
        character
        for character in filename
        if ord(character) >= 32 and ord(character) != 127
    )
    if not sanitized:
        sanitized = "download"
    fallback = "".join(
        character
        if character.isascii()
        and (character.isalnum() or character in "._- ()")
        else "_"
        for character in sanitized
    ).strip()
    if not fallback.strip("._"):
        fallback = "download"
    encoded = quote(sanitized, safe="")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    conversation_id: UUID,
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File()],
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> DocumentResponse:
    content = await file.read(DOCUMENT_MAX_SIZE_BYTES + 1)
    async with runtime.transaction() as session:
        document = await _service(session).upload(
            organization_id,
            account_id,
            conversation_id,
            kind,
            file.filename or "",
            file.content_type,
            content,
            DOCUMENT_MAX_SIZE_BYTES,
            now,
        )
    return DocumentResponse.model_validate(document)


@router.get("", response_model=DocumentPageResponse)
async def list_documents(
    conversation_id: UUID,
    query: Annotated[DocumentPageQuery, Depends()],
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> DocumentPageResponse:
    async with runtime.transaction() as session:
        documents, next_cursor = await _service(session).list(
            organization_id,
            account_id,
            conversation_id,
            cursor=query.cursor,
            limit=query.limit,
        )
    return DocumentPageResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        next_cursor=next_cursor,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    conversation_id: UUID,
    document_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> DocumentResponse:
    async with runtime.transaction() as session:
        document = await _service(session).get(
            organization_id,
            account_id,
            conversation_id,
            document_id,
        )
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/content")
async def download_document(
    conversation_id: UUID,
    document_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> Response:
    async with runtime.transaction() as session:
        document = await _service(session).get(
            organization_id,
            account_id,
            conversation_id,
            document_id,
        )
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={"Content-Disposition": _content_disposition(document.filename)},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    conversation_id: UUID,
    document_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> None:
    async with runtime.transaction() as session:
        await _service(session).delete(
            organization_id,
            account_id,
            conversation_id,
            document_id,
        )
