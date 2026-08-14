"""Leave document uploaded and deleted letters beside the file row."""

from datetime import datetime
from uuid import uuid4

from trialscribe_events.contracts.document import DocumentDeleted, DocumentUploaded
from trialscribe_events.registry import EventRegistry
from trialscribe_events.repositories.outbox import OutboxRepository
from trialscribe_events.utils.constant import (
    DOCUMENT_DELETED_EVENT_TYPE,
    DOCUMENT_EVENT_VERSION,
    DOCUMENT_UPLOADED_EVENT_TYPE,
)

from trialscribe_ai.models.document import Document
from trialscribe_ai.utils.constant import SERVICE_NAME


class DocumentEventPublisher:
    """Write document letters into the caller's outbox transaction."""

    def __init__(
        self,
        outbox: OutboxRepository,
        registry: EventRegistry,
        topic_prefix: str,
    ) -> None:
        self._outbox = outbox
        self._registry = registry
        self._topic_prefix = topic_prefix

    async def record_uploaded(self, document: Document, now: datetime) -> None:
        """Announce a stored file so the worker can index it."""

        await self._enqueue(
            DOCUMENT_UPLOADED_EVENT_TYPE,
            document,
            now,
            DocumentUploaded(
                document_id=document.id,
                conversation_id=document.conversation_id,
                organization_id=document.organization_id,
                uploaded_by_account_id=document.uploaded_by_account_id
                if document.uploaded_by_account_id is not None
                else document.id,
                kind=document.kind,
            ),
        )

    async def record_deleted(self, document: Document, now: datetime) -> None:
        """Announce a removed file so the worker can drop its passages."""

        await self._enqueue(
            DOCUMENT_DELETED_EVENT_TYPE,
            document,
            now,
            DocumentDeleted(
                document_id=document.id,
                conversation_id=document.conversation_id,
                organization_id=document.organization_id,
                kind=document.kind,
            ),
        )

    async def _enqueue(
        self,
        event_type: str,
        document: Document,
        now: datetime,
        payload: DocumentUploaded | DocumentDeleted,
    ) -> None:
        envelope = self._registry.build(
            event_type=event_type,
            version=DOCUMENT_EVENT_VERSION,
            organization_id=document.organization_id,
            subject=str(document.id),
            correlation_id=uuid4(),
            producer=SERVICE_NAME,
            occurred_at=now,
            payload=payload,
        )
        await self._outbox.enqueue(
            self._registry.topic_of(self._topic_prefix, envelope),
            envelope,
        )
