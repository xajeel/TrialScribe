"""Authorize and load cited passages for one conversation."""

from uuid import UUID

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.evidence_chunk import EvidenceChunk
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_ai.utils.constant import MAX_EVIDENCE_CHUNK_IDS
from trialscribe_ai.utils.exceptions import (
    ConversationNotFoundError,
    InvalidEvidenceRequestError,
)


class EvidenceService:
    """Read stored passages through injected repositories."""

    def __init__(
        self,
        conversations: ConversationRepository,
        chunks: EvidenceChunkRepository,
    ) -> None:
        self._conversations = conversations
        self._chunks = chunks

    async def get_many(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        ids: list[UUID],
    ) -> list[EvidenceChunk]:
        if not 1 <= len(ids) <= MAX_EVIDENCE_CHUNK_IDS:
            raise InvalidEvidenceRequestError
        await self._require_accessible(organization_id, account_id, conversation_id)
        return await self._chunks.get_scoped(
            organization_id,
            conversation_id,
            ids,
        )

    async def _require_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
    ) -> Conversation:
        conversation = await self._conversations.get_accessible(
            organization_id,
            account_id,
            conversation_id,
        )
        if conversation is None:
            raise ConversationNotFoundError
        return conversation
