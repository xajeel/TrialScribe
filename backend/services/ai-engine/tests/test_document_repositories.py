import asyncio
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.models.document import Document
from trialscribe_ai.repositories.documents import (
    DocumentRepository,
    _decode_cursor,
    _encode_cursor,
)
from trialscribe_ai.utils.exceptions import InvalidCursorError

ORGANIZATION_ID = UUID("21000000-0000-4000-8000-000000000001")
CONVERSATION_ID = UUID("21000000-0000-4000-8000-000000000002")


def test_document_cursor_round_trips_and_rejects_bad_input() -> None:
    created_at = datetime(2026, 7, 24, 8, 30, tzinfo=UTC)
    document_id = uuid4()

    cursor = _encode_cursor(created_at, document_id)

    assert _decode_cursor(cursor) == (created_at, document_id)
    assert str(document_id) not in cursor
    with pytest.raises(InvalidCursorError):
        _decode_cursor("not-a-cursor")


def test_get_scoped_filters_tenant_and_conversation() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    repository = DocumentRepository(session)

    asyncio.run(repository.get_scoped(ORGANIZATION_ID, CONVERSATION_ID, uuid4()))

    statement = str(session.scalar.await_args.args[0])
    assert "documents.organization_id" in statement
    assert "documents.conversation_id" in statement


def test_document_page_uses_limit_plus_one_and_deterministic_cursor() -> None:
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    documents = [
        Document(
            id=uuid4(),
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            uploaded_by_account_id=None,
            kind="research_document",
            filename=f"doc-{index}.pdf",
            content_type="application/pdf",
            byte_size=10,
            status="pending",
            content=b"%PDF-1.4",
            created_at=now - timedelta(minutes=index),
            updated_at=now,
        )
        for index in range(3)
    ]
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = documents
    repository = DocumentRepository(session)

    items, cursor = asyncio.run(
        repository.list_scoped(
            ORGANIZATION_ID,
            CONVERSATION_ID,
            cursor=None,
            limit=2,
        )
    )

    assert items == documents[:2]
    assert cursor is not None
    assert _decode_cursor(cursor) == (documents[1].created_at, documents[1].id)
    statement = session.scalars.await_args.args[0]
    assert statement._limit_clause.value == 3
    assert re.search(r"\bdocuments\.content\b", str(statement)) is None
