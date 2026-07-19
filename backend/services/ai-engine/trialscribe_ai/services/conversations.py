"""Conversation workspace authorization and durable-memory use cases."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.conversation_message import ConversationMessage
from trialscribe_ai.repositories.conversation_access import (
    ConversationAccessRepository,
)
from trialscribe_ai.repositories.conversation_messages import (
    ConversationMessageRepository,
)
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.utils.constant import (
    COLLABORATOR_LIMIT,
    CONVERSATION_CONTENT_MAX_LENGTH,
    CONVERSATION_TITLE_MAX_LENGTH,
    MAX_PAGE_LIMIT,
)
from trialscribe_ai.utils.enum import MessageRole
from trialscribe_ai.utils.exceptions import (
    CollaboratorConflictError,
    ConversationArchivedError,
    ConversationNotFoundError,
    ConversationPermissionDeniedError,
    InvalidConversationInputError,
)

ConversationRecord = tuple[Conversation, list[UUID]]


class ConversationService:
    """Manage tenant-safe conversations through injected repositories."""

    def __init__(
        self,
        conversations: ConversationRepository,
        access: ConversationAccessRepository,
        messages: ConversationMessageRepository,
    ) -> None:
        self._conversations = conversations
        self._access = access
        self._messages = messages

    async def create_conversation(
        self,
        organization_id: UUID,
        account_id: UUID,
        title: str,
        now: datetime,
    ) -> ConversationRecord:
        normalized_title = self._normalize_title(title)
        conversation = await self._conversations.add(
            Conversation(
                organization_id=organization_id,
                owner_account_id=account_id,
                title=normalized_title,
                last_activity_at=now,
            )
        )
        try:
            await self._access.add(conversation.id, organization_id, account_id)
        except IntegrityError:
            raise CollaboratorConflictError from None
        return conversation, []

    async def list_conversations(
        self,
        organization_id: UUID,
        account_id: UUID,
        *,
        archived: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ConversationRecord], str | None]:
        self._validate_limit(limit)
        conversations, next_cursor = await self._conversations.list_accessible(
            organization_id,
            account_id,
            archived=archived,
            cursor=cursor,
            limit=limit,
        )
        records = [
            (
                conversation,
                await self._access.list_collaborator_ids(
                    conversation.id,
                    organization_id,
                    conversation.owner_account_id,
                ),
            )
            for conversation in conversations
        ]
        return records, next_cursor

    async def get_conversation(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
    ) -> ConversationRecord:
        conversation = await self._require_accessible(
            organization_id,
            account_id,
            conversation_id,
        )
        return conversation, await self._collaborators(conversation)

    async def rename_conversation(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> ConversationRecord:
        conversation = await self._require_owner(
            organization_id,
            account_id,
            conversation_id,
        )
        conversation.title = self._normalize_title(title)
        await self._conversations.flush(conversation)
        return conversation, await self._collaborators(conversation)

    async def archive_conversation(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        now: datetime,
    ) -> ConversationRecord:
        conversation = await self._require_owner(
            organization_id,
            account_id,
            conversation_id,
        )
        if conversation.archived_at is None:
            conversation.archived_at = now
            await self._conversations.flush(conversation)
        return conversation, await self._collaborators(conversation)

    async def restore_conversation(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
    ) -> ConversationRecord:
        conversation = await self._require_owner(
            organization_id,
            account_id,
            conversation_id,
        )
        if conversation.archived_at is not None:
            conversation.archived_at = None
            await self._conversations.flush(conversation)
        return conversation, await self._collaborators(conversation)

    async def replace_collaborators(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        collaborator_account_ids: list[UUID],
    ) -> ConversationRecord:
        if len(collaborator_account_ids) > COLLABORATOR_LIMIT or len(
            collaborator_account_ids
        ) != len(set(collaborator_account_ids)):
            raise InvalidConversationInputError
        conversation = await self._require_owner(
            organization_id,
            account_id,
            conversation_id,
        )
        collaborators = sorted(
            (
                candidate
                for candidate in collaborator_account_ids
                if candidate != conversation.owner_account_id
            ),
            key=str,
        )
        try:
            await self._access.replace_collaborators(
                conversation.id,
                organization_id,
                conversation.owner_account_id,
                collaborators,
            )
        except IntegrityError:
            raise CollaboratorConflictError from None
        return conversation, collaborators

    async def append_user_message(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        content: str,
        now: datetime,
    ) -> ConversationMessage:
        return await self._append_message(
            organization_id,
            account_id,
            conversation_id,
            content,
            MessageRole.USER,
            account_id,
            now,
        )

    async def append_assistant_message(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        content: str,
        now: datetime,
    ) -> ConversationMessage:
        return await self._append_message(
            organization_id,
            account_id,
            conversation_id,
            content,
            MessageRole.ASSISTANT,
            None,
            now,
        )

    async def list_messages(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ConversationMessage], str | None]:
        self._validate_limit(limit)
        await self._require_accessible(
            organization_id,
            account_id,
            conversation_id,
        )
        return await self._messages.list_for_conversation(
            conversation_id,
            organization_id,
            cursor=cursor,
            limit=limit,
        )

    async def _append_message(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        content: str,
        role: MessageRole,
        author_account_id: UUID | None,
        now: datetime,
    ) -> ConversationMessage:
        normalized_content = self._normalize_content(content)
        conversation = await self._conversations.get_accessible(
            organization_id,
            account_id,
            conversation_id,
            for_update=True,
        )
        if conversation is None:
            raise ConversationNotFoundError
        if conversation.archived_at is not None:
            raise ConversationArchivedError
        conversation.last_activity_at = now
        await self._conversations.flush(conversation)
        return await self._messages.append(
            conversation.id,
            organization_id,
            author_account_id,
            role.value,
            normalized_content,
            now,
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

    async def _require_owner(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
    ) -> Conversation:
        conversation = await self._require_accessible(
            organization_id,
            account_id,
            conversation_id,
        )
        if conversation.owner_account_id != account_id:
            raise ConversationPermissionDeniedError
        return conversation

    async def _collaborators(self, conversation: Conversation) -> list[UUID]:
        return await self._access.list_collaborator_ids(
            conversation.id,
            conversation.organization_id,
            conversation.owner_account_id,
        )

    @staticmethod
    def _normalize_title(title: str) -> str:
        normalized = title.strip()
        if not 1 <= len(normalized) <= CONVERSATION_TITLE_MAX_LENGTH:
            raise InvalidConversationInputError
        return normalized

    @staticmethod
    def _normalize_content(content: str) -> str:
        normalized = content.strip()
        if not 1 <= len(normalized) <= CONVERSATION_CONTENT_MAX_LENGTH:
            raise InvalidConversationInputError
        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise InvalidConversationInputError
