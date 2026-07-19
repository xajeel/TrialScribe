import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.conversation_message import ConversationMessage
from trialscribe_ai.services.conversations import ConversationService
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    ConversationPermissionDeniedError,
    InvalidConversationInputError,
)

NOW = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("30000000-0000-4000-8000-000000000001")
OTHER_ORGANIZATION_ID = UUID("30000000-0000-4000-8000-000000000002")
OWNER_ID = UUID("30000000-0000-4000-8000-000000000003")
COLLABORATOR_ID = UUID("30000000-0000-4000-8000-000000000004")
STRANGER_ID = UUID("30000000-0000-4000-8000-000000000005")


class FakeConversationRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Conversation] = {}
        self.locked = False

    async def add(self, conversation: Conversation) -> Conversation:
        conversation.id = uuid4()
        conversation.created_at = NOW
        conversation.updated_at = NOW
        self.items[conversation.id] = conversation
        return conversation

    async def get_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        conversation = self.items.get(conversation_id)
        if conversation is None or conversation.organization_id != organization_id:
            return None
        allowed = account_id == conversation.owner_account_id or account_id in ACCESS.grants.get(
            conversation_id, set()
        )
        self.locked = for_update
        return conversation if allowed else None

    async def list_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        *,
        archived: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Conversation], str | None]:
        del cursor
        items = [
            item
            for item in self.items.values()
            if item.organization_id == organization_id
            and (item.owner_account_id == account_id or account_id in ACCESS.grants[item.id])
            and (item.archived_at is not None) is archived
        ]
        return items[:limit], None

    async def flush(self, conversation: Conversation) -> Conversation:
        return conversation


class FakeAccessRepository:
    def __init__(self) -> None:
        self.grants: dict[UUID, set[UUID]] = {}

    async def add(
        self,
        conversation_id: UUID,
        _organization_id: UUID,
        account_id: UUID,
    ) -> object:
        self.grants.setdefault(conversation_id, set()).add(account_id)
        return object()

    async def list_collaborator_ids(
        self,
        conversation_id: UUID,
        _organization_id: UUID,
        owner_account_id: UUID,
    ) -> list[UUID]:
        return sorted(self.grants[conversation_id] - {owner_account_id}, key=str)

    async def replace_collaborators(
        self,
        conversation_id: UUID,
        _organization_id: UUID,
        owner_account_id: UUID,
        account_ids: list[UUID],
    ) -> None:
        self.grants[conversation_id] = {owner_account_id, *account_ids}


class FakeMessageRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, list[ConversationMessage]] = {}

    async def append(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        author_account_id: UUID | None,
        role: str,
        content: str,
        activity_at: datetime,
    ) -> ConversationMessage:
        history = self.items.setdefault(conversation_id, [])
        message = ConversationMessage(
            id=uuid4(),
            conversation_id=conversation_id,
            organization_id=organization_id,
            author_account_id=author_account_id,
            role=role,
            content=content,
            sequence=len(history) + 1,
            created_at=activity_at,
            updated_at=activity_at,
        )
        history.append(message)
        return message

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        _organization_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ConversationMessage], str | None]:
        del cursor
        return self.items.get(conversation_id, [])[:limit], None


def service_context() -> tuple[
    ConversationService,
    FakeConversationRepository,
    FakeAccessRepository,
    FakeMessageRepository,
]:
    global ACCESS
    conversations = FakeConversationRepository()
    ACCESS = FakeAccessRepository()
    messages = FakeMessageRepository()
    return (
        ConversationService(conversations, ACCESS, messages),  # type: ignore[arg-type]
        conversations,
        ACCESS,
        messages,
    )


ACCESS = FakeAccessRepository()


def create_workspace() -> tuple[
    ConversationService,
    Conversation,
    FakeConversationRepository,
    FakeAccessRepository,
    FakeMessageRepository,
]:
    service, conversations, access, messages = service_context()
    conversation, collaborators = asyncio.run(
        service.create_conversation(ORGANIZATION_ID, OWNER_ID, "  Protocol  ", NOW)
    )
    assert collaborators == []
    return service, conversation, conversations, access, messages


def test_creator_shares_and_collaborator_can_resume_but_not_manage() -> None:
    service, conversation, _, _, _ = create_workspace()
    shared, collaborators = asyncio.run(
        service.replace_collaborators(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            [OWNER_ID, COLLABORATOR_ID],
        )
    )

    message = asyncio.run(
        service.append_user_message(
            ORGANIZATION_ID,
            COLLABORATOR_ID,
            conversation.id,
            " Continue this ",
            NOW,
        )
    )

    assert shared is conversation
    assert collaborators == [COLLABORATOR_ID]
    assert message.author_account_id == COLLABORATOR_ID
    assert message.content == "Continue this"
    with pytest.raises(ConversationPermissionDeniedError):
        asyncio.run(
            service.rename_conversation(
                ORGANIZATION_ID,
                COLLABORATOR_ID,
                conversation.id,
                "Forbidden",
            )
        )


def test_archive_is_idempotent_blocks_append_and_restore_preserves_history() -> None:
    service, conversation, _, _, messages = create_workspace()
    original = asyncio.run(
        service.append_assistant_message(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "Draft",
            NOW,
        )
    )
    asyncio.run(
        service.archive_conversation(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            NOW,
        )
    )
    archived_at = conversation.archived_at
    asyncio.run(
        service.archive_conversation(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            NOW,
        )
    )

    with pytest.raises(ConversationArchivedError):
        asyncio.run(
            service.append_user_message(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "Blocked",
                NOW,
            )
        )
    asyncio.run(
        service.restore_conversation(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
        )
    )

    assert archived_at == NOW
    assert conversation.archived_at is None
    assert messages.items[conversation.id] == [original]
    assert original.author_account_id is None


def test_foreign_tenant_unshared_and_invalid_content_are_hidden_or_rejected() -> None:
    service, conversation, _, _, _ = create_workspace()

    for organization_id, account_id in (
        (OTHER_ORGANIZATION_ID, OWNER_ID),
        (ORGANIZATION_ID, STRANGER_ID),
    ):
        with pytest.raises(ConversationNotFoundError):
            asyncio.run(
                service.get_conversation(
                    organization_id,
                    account_id,
                    conversation.id,
                )
            )
    with pytest.raises(InvalidConversationInputError):
        asyncio.run(
            service.append_user_message(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "   ",
                NOW,
            )
        )
