import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.repositories.conversation_messages import (
    ConversationMessageRepository,
    _decode_cursor as decode_message_cursor,
    _encode_cursor as encode_message_cursor,
)
from trialscribe_ai.repositories.conversations import (
    ConversationRepository,
    _decode_cursor as decode_conversation_cursor,
    _encode_cursor as encode_conversation_cursor,
)
from trialscribe_ai.utils.exceptions import InvalidCursorError

ORGANIZATION_ID = UUID("20000000-0000-4000-8000-000000000001")
ACCOUNT_ID = UUID("20000000-0000-4000-8000-000000000002")


def test_cursors_are_opaque_round_trippable_and_strict() -> None:
    activity_at = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)
    conversation_id = uuid4()

    conversation_cursor = encode_conversation_cursor(activity_at, conversation_id)
    message_cursor = encode_message_cursor(42)

    assert decode_conversation_cursor(conversation_cursor) == (
        activity_at,
        conversation_id,
    )
    assert decode_message_cursor(message_cursor) == 42
    assert str(conversation_id) not in conversation_cursor
    with pytest.raises(InvalidCursorError):
        decode_conversation_cursor("not-a-cursor")
    with pytest.raises(InvalidCursorError):
        decode_message_cursor("e30")


def test_accessible_lookup_always_scopes_tenant_account_and_row_lock() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    repository = ConversationRepository(session)

    asyncio.run(
        repository.get_accessible(
            ORGANIZATION_ID,
            ACCOUNT_ID,
            uuid4(),
            for_update=True,
        )
    )

    statement = str(session.scalar.await_args.args[0])
    assert "conversations.organization_id" in statement
    assert "conversation_access.account_id" in statement
    assert "FOR UPDATE" in statement


def test_conversation_page_uses_limit_plus_one_and_deterministic_cursor() -> None:
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    conversations = [
        Conversation(
            id=uuid4(),
            organization_id=ORGANIZATION_ID,
            owner_account_id=ACCOUNT_ID,
            title=f"Conversation {index}",
            last_activity_at=now - timedelta(minutes=index),
        )
        for index in range(3)
    ]
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = conversations
    repository = ConversationRepository(session)

    items, cursor = asyncio.run(
        repository.list_accessible(
            ORGANIZATION_ID,
            ACCOUNT_ID,
            archived=False,
            cursor=None,
            limit=2,
        )
    )

    assert items == conversations[:2]
    assert cursor is not None
    assert decode_conversation_cursor(cursor) == (
        conversations[1].last_activity_at,
        conversations[1].id,
    )
    statement = session.scalars.await_args.args[0]
    assert statement._limit_clause.value == 3


def test_message_page_cursor_uses_last_returned_sequence() -> None:
    messages = []
    for sequence in range(1, 4):
        message = AsyncMock()
        message.sequence = sequence
        messages.append(message)
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = messages
    repository = ConversationMessageRepository(session)

    items, cursor = asyncio.run(
        repository.list_for_conversation(
            uuid4(),
            ORGANIZATION_ID,
            cursor=None,
            limit=2,
        )
    )

    assert items == messages[:2]
    assert cursor is not None
    assert decode_message_cursor(cursor) == 2
