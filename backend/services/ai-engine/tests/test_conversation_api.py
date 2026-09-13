from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from trialscribe_ai.api import conversations as routes
from trialscribe_ai.api.app import app
from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
)
from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.conversation_message import ConversationMessage
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    ConversationPermissionDeniedError,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("40000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("40000000-0000-4000-8000-000000000002")
CONVERSATION_ID = UUID("40000000-0000-4000-8000-000000000003")
COLLABORATOR_ID = UUID("40000000-0000-4000-8000-000000000004")
MESSAGE_ID = UUID("40000000-0000-4000-8000-000000000005")


class FakeDatabaseRuntime:
    @asynccontextmanager
    async def transaction(self) -> Any:
        yield object()


class FakeConversationService:
    def __init__(self) -> None:
        self.conversation = Conversation(
            id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            owner_account_id=ACCOUNT_ID,
            title="Protocol",
            last_activity_at=NOW,
            archived_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.collaborators = [COLLABORATOR_ID]
        self.message = ConversationMessage(
            id=MESSAGE_ID,
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            author_account_id=ACCOUNT_ID,
            role="user",
            content="Continue",
            sequence=1,
            created_at=NOW,
            updated_at=NOW,
        )

    async def create_conversation(self, *_args: object) -> tuple[Conversation, list[UUID]]:
        return self.conversation, self.collaborators

    async def list_conversations(
        self, *_args: object, **_kwargs: object
    ) -> tuple[list[tuple[Conversation, list[UUID]]], str | None]:
        return [(self.conversation, self.collaborators)], "next-conversation"

    async def get_conversation(self, *_args: object) -> tuple[Conversation, list[UUID]]:
        return self.conversation, self.collaborators

    async def rename_conversation(
        self, *_args: object
    ) -> tuple[Conversation, list[UUID]]:
        self.conversation.title = "Renamed"
        return self.conversation, self.collaborators

    async def archive_conversation(
        self, *_args: object
    ) -> tuple[Conversation, list[UUID]]:
        self.conversation.archived_at = NOW
        return self.conversation, self.collaborators

    async def restore_conversation(
        self, *_args: object
    ) -> tuple[Conversation, list[UUID]]:
        self.conversation.archived_at = None
        return self.conversation, self.collaborators

    async def replace_collaborators(
        self, *_args: object
    ) -> tuple[Conversation, list[UUID]]:
        return self.conversation, self.collaborators

    async def append_user_message(self, *_args: object) -> ConversationMessage:
        return self.message

    async def list_messages(
        self, *_args: object, **_kwargs: object
    ) -> tuple[list[ConversationMessage], str | None]:
        return [self.message], "next-message"


@pytest.fixture
def api_context(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeConversationService]:
    service = FakeConversationService()
    monkeypatch.setattr(routes, "ConversationService", lambda *_args: service)
    app.dependency_overrides[get_current_account_id] = lambda: ACCOUNT_ID
    app.dependency_overrides[get_current_organization_id] = lambda: ORGANIZATION_ID
    app.dependency_overrides[get_database_runtime] = lambda: FakeDatabaseRuntime()
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        yield TestClient(app), service
    finally:
        app.dependency_overrides.clear()


def test_trusted_headers_are_required_and_malformed_values_are_safe() -> None:
    client = TestClient(app)
    missing = client.get("/conversations")
    malformed_account = client.get(
        "/conversations",
        headers={
            "X-TrialScribe-Account-ID": "secret-not-a-uuid",
            "X-TrialScribe-Organization-ID": str(ORGANIZATION_ID),
        },
    )

    assert missing.status_code in {401, 422}
    assert malformed_account.status_code == 422
    assert malformed_account.json() == {"detail": "Invalid account context"}
    assert "secret-not-a-uuid" not in malformed_account.text


def test_conversation_lifecycle_contracts(api_context: tuple[TestClient, object]) -> None:
    client, _ = api_context

    created = client.post("/conversations", json={"title": " Protocol "})
    listed = client.get("/conversations?limit=20")
    fetched = client.get(f"/conversations/{CONVERSATION_ID}")
    renamed = client.patch(
        f"/conversations/{CONVERSATION_ID}", json={"title": "Renamed"}
    )
    archived = client.delete(f"/conversations/{CONVERSATION_ID}")
    restored = client.post(f"/conversations/{CONVERSATION_ID}/restore")
    shared = client.put(
        f"/conversations/{CONVERSATION_ID}/collaborators",
        json={"account_ids": [str(COLLABORATOR_ID)]},
    )

    assert created.status_code == 201
    assert created.json()["organization_id"] == str(ORGANIZATION_ID)
    assert listed.json()["next_cursor"] == "next-conversation"
    assert fetched.json()["collaborator_account_ids"] == [str(COLLABORATOR_ID)]
    assert renamed.json()["title"] == "Renamed"
    assert archived.json()["status"] == "archived"
    assert restored.json()["status"] == "active"
    assert shared.status_code == 200


def test_message_contract_accepts_user_content_only(
    api_context: tuple[TestClient, object],
) -> None:
    client, _ = api_context

    created = client.post(
        f"/conversations/{CONVERSATION_ID}/messages",
        json={"content": " Continue "},
    )
    forged = client.post(
        f"/conversations/{CONVERSATION_ID}/messages",
        json={"content": "Continue", "role": "assistant"},
    )
    listed = client.get(f"/conversations/{CONVERSATION_ID}/messages")

    assert created.status_code == 201
    assert created.json()["role"] == "user"
    assert "role" not in routes.ConversationMessageCreateRequest.model_fields
    assert forged.status_code == 201
    assert listed.json()["items"][0]["sequence"] == 1
    assert listed.json()["next_cursor"] == "next-message"


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (ConversationNotFoundError("postgresql://secret"), 404, "Conversation not found"),
        (
            ConversationPermissionDeniedError("private detail"),
            403,
            "Conversation permission denied",
        ),
        (ConversationArchivedError("private detail"), 409, "Conversation is archived"),
    ],
)
def test_service_errors_are_allow_listed(
    api_context: tuple[TestClient, FakeConversationService],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    client, service = api_context

    async def fail(*_args: object) -> object:
        raise error

    monkeypatch.setattr(service, "get_conversation", fail)
    response = client.get(f"/conversations/{CONVERSATION_ID}")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert str(error) not in response.text


def test_validation_response_never_echoes_message_content(
    api_context: tuple[TestClient, object],
) -> None:
    secret = "sensitive-content-" + ("x" * 20_100)
    response = api_context[0].post(
        f"/conversations/{CONVERSATION_ID}/messages",
        json={"content": secret},
    )

    assert response.status_code == 422
    assert secret not in response.text
    assert "input" not in response.text
