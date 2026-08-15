import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.document import Document
from trialscribe_ai.services.documents import DocumentService
from trialscribe_ai.utils.enum import DocumentKind
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    DocumentNotFoundError,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidTrialDataError,
    UnsupportedDocumentTypeError,
)

NOW = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("22000000-0000-4000-8000-000000000001")
OWNER_ID = UUID("22000000-0000-4000-8000-000000000002")
CONVERSATION_ID = UUID("22000000-0000-4000-8000-000000000003")
MAX_SIZE = 1_000


class FakeConversationRepository:
    def __init__(self, conversation: Conversation | None) -> None:
        self.conversation = conversation
        self.flushed = False

    async def get_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        del account_id, for_update
        conversation = self.conversation
        if conversation is None:
            return None
        if (
            conversation.organization_id != organization_id
            or conversation.id != conversation_id
        ):
            return None
        return conversation

    async def flush(self, conversation: Conversation) -> Conversation:
        self.flushed = True
        return conversation


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Document] = {}

    async def add(self, document: Document) -> Document:
        document.id = uuid4()
        document.created_at = NOW
        document.updated_at = NOW
        self.items[document.id] = document
        return document

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
    ) -> Document | None:
        document = self.items.get(document_id)
        if document is None:
            return None
        if (
            document.organization_id != organization_id
            or document.conversation_id != conversation_id
        ):
            return None
        return document

    async def list_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Document], str | None]:
        del cursor
        items = [
            document
            for document in self.items.values()
            if document.organization_id == organization_id
            and document.conversation_id == conversation_id
        ]
        return items[:limit], None

    async def delete(self, document: Document) -> None:
        self.items.pop(document.id, None)


class FakeEvents:
    def __init__(self) -> None:
        self.uploaded: list[Document] = []
        self.deleted: list[Document] = []

    async def record_uploaded(self, document: Document, now: datetime) -> None:
        del now
        self.uploaded.append(document)

    async def record_deleted(self, document: Document, now: datetime) -> None:
        del now
        self.deleted.append(document)


def make_conversation(*, archived: bool = False) -> Conversation:
    return Conversation(
        id=CONVERSATION_ID,
        organization_id=ORGANIZATION_ID,
        owner_account_id=OWNER_ID,
        title="Protocol",
        last_activity_at=NOW,
        archived_at=NOW if archived else None,
        created_at=NOW,
        updated_at=NOW,
    )


def service_with(
    conversation: Conversation | None,
) -> tuple[DocumentService, FakeConversationRepository, FakeDocumentRepository, FakeEvents]:
    conversations = FakeConversationRepository(conversation)
    documents = FakeDocumentRepository()
    events = FakeEvents()
    service = DocumentService(conversations, documents, events)  # type: ignore[arg-type]
    return service, conversations, documents, events


def upload(
    service: DocumentService,
    *,
    kind: DocumentKind,
    filename: str,
    content_type: str | None,
    content: bytes,
    max_size: int = MAX_SIZE,
) -> Document:
    return asyncio.run(
        service.upload(
            ORGANIZATION_ID,
            OWNER_ID,
            CONVERSATION_ID,
            kind,
            filename,
            content_type,
            content,
            max_size,
            NOW,
        )
    )


def test_upload_accepts_trial_json_pdf_and_text() -> None:
    service, conversations, documents, events = service_with(make_conversation())

    trial = upload(
        service,
        kind=DocumentKind.TRIAL_DATA,
        filename="trial.json",
        content_type="application/octet-stream",
        content=b'{"nct": "NCT01"}',
    )
    pdf = upload(
        service,
        kind=DocumentKind.RESEARCH_DOCUMENT,
        filename="paper.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.7 body",
    )
    markdown = upload(
        service,
        kind=DocumentKind.RESEARCH_DOCUMENT,
        filename="notes.md",
        content_type="text/markdown",
        content="# Notes".encode(),
    )

    assert trial.content_type == "application/json"
    assert trial.status == "pending"
    assert trial.uploaded_by_account_id == OWNER_ID
    assert trial.byte_size == len(b'{"nct": "NCT01"}')
    assert pdf.content_type == "application/pdf"
    assert markdown.content_type == "text/markdown"
    assert conversations.flushed is True
    assert len(documents.items) == 3
    assert len(events.uploaded) == 3


def test_upload_rejects_invalid_content() -> None:
    service, _, _, events = service_with(make_conversation())

    with pytest.raises(EmptyDocumentError):
        upload(
            service,
            kind=DocumentKind.RESEARCH_DOCUMENT,
            filename="empty.pdf",
            content_type="application/pdf",
            content=b"",
        )
    with pytest.raises(DocumentTooLargeError):
        upload(
            service,
            kind=DocumentKind.RESEARCH_DOCUMENT,
            filename="big.txt",
            content_type="text/plain",
            content=b"x" * (MAX_SIZE + 1),
        )
    with pytest.raises(UnsupportedDocumentTypeError):
        upload(
            service,
            kind=DocumentKind.RESEARCH_DOCUMENT,
            filename="tool.exe",
            content_type="application/x-msdownload",
            content=b"MZ binary",
        )
    with pytest.raises(UnsupportedDocumentTypeError):
        upload(
            service,
            kind=DocumentKind.RESEARCH_DOCUMENT,
            filename="fake.pdf",
            content_type="application/pdf",
            content=b"not really a pdf",
        )
    with pytest.raises(InvalidTrialDataError):
        upload(
            service,
            kind=DocumentKind.TRIAL_DATA,
            filename="array.json",
            content_type="application/json",
            content=b"[1, 2, 3]",
        )
    with pytest.raises(InvalidTrialDataError):
        upload(
            service,
            kind=DocumentKind.TRIAL_DATA,
            filename="bad.json",
            content_type="application/json",
            content=b"not json",
        )

    assert events.uploaded == []
    assert events.deleted == []


def test_upload_rejects_html_pdf_polyglot() -> None:
    service, _, _, events = service_with(make_conversation())

    with pytest.raises(UnsupportedDocumentTypeError):
        upload(
            service,
            kind=DocumentKind.RESEARCH_DOCUMENT,
            filename="polyglot.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.7\n<!DOCTYPE html>",
        )
    with pytest.raises(UnsupportedDocumentTypeError):
        upload(
            service,
            kind=DocumentKind.RESEARCH_DOCUMENT,
            filename="script.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.7\n<script>",
        )

    assert events.uploaded == []


def test_upload_requires_accessible_active_conversation() -> None:
    absent_service, _, _, absent_events = service_with(None)
    with pytest.raises(ConversationNotFoundError):
        upload(
            absent_service,
            kind=DocumentKind.TRIAL_DATA,
            filename="trial.json",
            content_type="application/json",
            content=b"{}",
        )
    assert absent_events.uploaded == []

    archived_service, _, _, archived_events = service_with(
        make_conversation(archived=True)
    )
    with pytest.raises(ConversationArchivedError):
        upload(
            archived_service,
            kind=DocumentKind.TRIAL_DATA,
            filename="trial.json",
            content_type="application/json",
            content=b"{}",
        )
    assert archived_events.uploaded == []


def test_get_and_delete_are_scoped() -> None:
    service, _, documents, events = service_with(make_conversation())
    created = upload(
        service,
        kind=DocumentKind.TRIAL_DATA,
        filename="trial.json",
        content_type="application/json",
        content=b"{}",
    )

    fetched = asyncio.run(
        service.get(ORGANIZATION_ID, OWNER_ID, CONVERSATION_ID, created.id)
    )
    assert fetched.id == created.id
    with pytest.raises(DocumentNotFoundError):
        asyncio.run(service.get(ORGANIZATION_ID, OWNER_ID, CONVERSATION_ID, uuid4()))

    asyncio.run(
        service.delete(ORGANIZATION_ID, OWNER_ID, CONVERSATION_ID, created.id, NOW)
    )
    assert documents.items == {}
    assert [item.id for item in events.deleted] == [created.id]
    with pytest.raises(DocumentNotFoundError):
        asyncio.run(
            service.delete(ORGANIZATION_ID, OWNER_ID, CONVERSATION_ID, created.id, NOW)
        )
