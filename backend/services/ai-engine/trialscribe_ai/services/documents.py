"""Conversation document ingestion authorization and validation use cases."""

import json
from datetime import datetime
from uuid import UUID

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.document import Document
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.repositories.documents import DocumentRepository
from trialscribe_ai.utils.constant import (
    ALLOWED_DOCUMENT_CONTENT_TYPES,
    FILENAME_MAX_LENGTH,
    MAX_PAGE_LIMIT,
    PDF_MAGIC,
    TRIAL_DATA_CONTENT_TYPE,
)
from trialscribe_ai.utils.enum import DocumentKind, DocumentStatus
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    DocumentNotFoundError,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidConversationInputError,
    InvalidTrialDataError,
    UnsupportedDocumentTypeError,
)

_PDF_CONTENT_TYPE = "application/pdf"


class DocumentService:
    """Ingest and manage conversation documents through injected repositories."""

    def __init__(
        self,
        conversations: ConversationRepository,
        documents: DocumentRepository,
    ) -> None:
        self._conversations = conversations
        self._documents = documents

    async def upload(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        kind: DocumentKind,
        filename: str,
        declared_content_type: str | None,
        content: bytes,
        max_size: int,
        now: datetime,
    ) -> Document:
        conversation = await self._require_accessible(
            organization_id,
            account_id,
            conversation_id,
            for_update=True,
        )
        if conversation.archived_at is not None:
            raise ConversationArchivedError
        if len(content) == 0:
            raise EmptyDocumentError
        if len(content) > max_size:
            raise DocumentTooLargeError
        normalized_filename = self._normalize_filename(filename)
        content_type = self._resolve_content_type(kind, declared_content_type, content)
        document = Document(
            conversation_id=conversation.id,
            organization_id=organization_id,
            uploaded_by_account_id=account_id,
            kind=kind.value,
            filename=normalized_filename,
            content_type=content_type,
            byte_size=len(content),
            status=DocumentStatus.PENDING.value,
            content=content,
        )
        conversation.last_activity_at = now
        await self._conversations.flush(conversation)
        return await self._documents.add(document)

    async def list(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Document], str | None]:
        self._validate_limit(limit)
        await self._require_accessible(organization_id, account_id, conversation_id)
        return await self._documents.list_scoped(
            organization_id,
            conversation_id,
            cursor=cursor,
            limit=limit,
        )

    async def get(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
    ) -> Document:
        await self._require_accessible(organization_id, account_id, conversation_id)
        document = await self._documents.get_scoped(
            organization_id,
            conversation_id,
            document_id,
        )
        if document is None:
            raise DocumentNotFoundError
        return document

    async def delete(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
    ) -> None:
        await self._require_accessible(organization_id, account_id, conversation_id)
        document = await self._documents.get_scoped(
            organization_id,
            conversation_id,
            document_id,
        )
        if document is None:
            raise DocumentNotFoundError
        await self._documents.delete(document)

    async def _require_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation:
        conversation = await self._conversations.get_accessible(
            organization_id,
            account_id,
            conversation_id,
            for_update=for_update,
        )
        if conversation is None:
            raise ConversationNotFoundError
        return conversation

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        normalized = filename.strip()
        if not 1 <= len(normalized) <= FILENAME_MAX_LENGTH:
            raise UnsupportedDocumentTypeError
        return normalized

    @staticmethod
    def _resolve_content_type(
        kind: DocumentKind,
        declared_content_type: str | None,
        content: bytes,
    ) -> str:
        if kind is DocumentKind.TRIAL_DATA:
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise InvalidTrialDataError from None
            if not isinstance(parsed, dict):
                raise InvalidTrialDataError
            return TRIAL_DATA_CONTENT_TYPE
        if declared_content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
            raise UnsupportedDocumentTypeError
        if declared_content_type == _PDF_CONTENT_TYPE:
            if not content.startswith(PDF_MAGIC):
                raise UnsupportedDocumentTypeError
        else:
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                raise UnsupportedDocumentTypeError from None
        return declared_content_type

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise InvalidConversationInputError
