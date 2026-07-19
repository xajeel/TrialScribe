"""Live conversation workspace checks driven by the isolated test script."""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_ai.api.app import app
from trialscribe_ai.repositories.conversation_access import ConversationAccessRepository
from trialscribe_ai.repositories.conversation_messages import ConversationMessageRepository
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.services.conversations import ConversationService

pytestmark = pytest.mark.integration

INTEGRATION_ENABLED = os.getenv("TRIALSCRIBE_AI_CONVERSATION_INTEGRATION") == "1"
PHASE = os.getenv("TRIALSCRIBE_AI_CONVERSATION_PHASE", "")
STATE_FILE = Path(os.getenv("TRIALSCRIBE_AI_CONVERSATION_STATE_FILE", "/nonexistent"))

OWNER_ID = UUID("50000000-0000-4000-8000-000000000001")
COLLABORATOR_ID = UUID("50000000-0000-4000-8000-000000000002")
STRANGER_ID = UUID("50000000-0000-4000-8000-000000000003")
FOREIGN_ID = UUID("50000000-0000-4000-8000-000000000004")
ORGANIZATION_ID = UUID("50000000-0000-4000-8000-000000000005")
FOREIGN_ORGANIZATION_ID = UUID("50000000-0000-4000-8000-000000000006")


def require_phase(expected: str) -> None:
    if not INTEGRATION_ENABLED or PHASE != expected:
        pytest.skip(f"requires conversation integration {expected} phase")


def headers(account_id: UUID, organization_id: UUID = ORGANIZATION_ID) -> dict[str, str]:
    return {
        "X-TrialScribe-Account-ID": str(account_id),
        "X-TrialScribe-Organization-ID": str(organization_id),
    }


async def seed_tenants() -> None:
    runtime = create_database_runtime(DatabaseSettings())
    try:
        async with runtime.transaction() as session:
            for account_id, email in (
                (OWNER_ID, "conversation-owner@example.com"),
                (COLLABORATOR_ID, "conversation-collaborator@example.com"),
                (STRANGER_ID, "conversation-stranger@example.com"),
                (FOREIGN_ID, "conversation-foreign@example.com"),
            ):
                await session.execute(
                    text(
                        "INSERT INTO trialscribe.accounts "
                        "(id, email, password_hash, is_active) "
                        "VALUES (:id, :email, :password_hash, true)"
                    ),
                    {
                        "id": account_id,
                        "email": email,
                        "password_hash": "integration-fixture-not-for-login",
                    },
                )
            for organization_id, name in (
                (ORGANIZATION_ID, "Conversation Research"),
                (FOREIGN_ORGANIZATION_ID, "Foreign Research"),
            ):
                await session.execute(
                    text(
                        "INSERT INTO trialscribe.organizations (id, name) "
                        "VALUES (:id, :name)"
                    ),
                    {"id": organization_id, "name": name},
                )
            for organization_id, account_id, role in (
                (ORGANIZATION_ID, OWNER_ID, "owner"),
                (ORGANIZATION_ID, COLLABORATOR_ID, "member"),
                (ORGANIZATION_ID, STRANGER_ID, "member"),
                (FOREIGN_ORGANIZATION_ID, FOREIGN_ID, "owner"),
            ):
                await session.execute(
                    text(
                        "INSERT INTO trialscribe.organization_memberships "
                        "(id, organization_id, account_id, role) "
                        "VALUES (:id, :organization_id, :account_id, :role)"
                    ),
                    {
                        "id": uuid4(),
                        "organization_id": organization_id,
                        "account_id": account_id,
                        "role": role,
                    },
                )
    finally:
        await runtime.dispose()


async def append_assistant_message(conversation_id: UUID) -> None:
    runtime = create_database_runtime(DatabaseSettings())
    try:
        async with runtime.transaction() as session:
            service = ConversationService(
                ConversationRepository(session),
                ConversationAccessRepository(session),
                ConversationMessageRepository(session),
            )
            await service.append_assistant_message(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation_id,
                "Assistant context",
                datetime.now(UTC),
            )
    finally:
        await runtime.dispose()


async def remove_collaborator_membership() -> None:
    runtime = create_database_runtime(DatabaseSettings())
    try:
        async with runtime.transaction() as session:
            await session.execute(
                text(
                    "DELETE FROM trialscribe.organization_memberships "
                    "WHERE organization_id = :organization_id AND account_id = :account_id"
                ),
                {
                    "organization_id": ORGANIZATION_ID,
                    "account_id": COLLABORATOR_ID,
                },
            )
    finally:
        await runtime.dispose()


def test_prepare_conversations_and_history() -> None:
    require_phase("prepare")
    asyncio.run(seed_tenants())

    with TestClient(app) as client:
        first = client.post(
            "/conversations",
            headers=headers(OWNER_ID),
            json={"title": "Primary Protocol"},
        )
        assert first.status_code == 201
        first_id = first.json()["id"]
        assert client.post(
            f"/conversations/{first_id}/messages",
            headers=headers(OWNER_ID),
            json={"content": "Owner context"},
        ).status_code == 201
        shared = client.put(
            f"/conversations/{first_id}/collaborators",
            headers=headers(OWNER_ID),
            json={"account_ids": [str(COLLABORATOR_ID)]},
        )
        assert shared.status_code == 200
        assert client.post(
            f"/conversations/{first_id}/messages",
            headers=headers(COLLABORATOR_ID),
            json={"content": "Collaborator context"},
        ).status_code == 201
        asyncio.run(append_assistant_message(UUID(first_id)))

        second = client.post(
            "/conversations",
            headers=headers(OWNER_ID),
            json={"title": "Secondary Protocol"},
        )
        assert second.status_code == 201
        archived = client.post(
            "/conversations",
            headers=headers(OWNER_ID),
            json={"title": "Archived Protocol"},
        )
        archived_id = archived.json()["id"]
        assert client.delete(
            f"/conversations/{archived_id}", headers=headers(OWNER_ID)
        ).status_code == 200

        owner_page = client.get(
            "/conversations?limit=1",
            headers=headers(OWNER_ID),
        )
        assert owner_page.status_code == 200
        assert owner_page.json()["next_cursor"] is not None
        assert client.get(
            f"/conversations/{first_id}", headers=headers(STRANGER_ID)
        ).status_code == 404
        assert client.get(
            f"/conversations/{first_id}",
            headers=headers(FOREIGN_ID, FOREIGN_ORGANIZATION_ID),
        ).status_code == 404

        state = {
            "first_id": first_id,
            "second_id": second.json()["id"],
            "archived_id": archived_id,
            "first_page_id": owner_page.json()["items"][0]["id"],
            "conversation_cursor": owner_page.json()["next_cursor"],
        }
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        STATE_FILE.chmod(0o600)


def test_verify_history_after_restart_and_membership_revocation() -> None:
    require_phase("verify")
    state: dict[str, str] = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        first = client.get(
            f"/conversations/{state['first_id']}",
            headers=headers(OWNER_ID),
        )
        assert first.status_code == 200
        assert first.json()["title"] == "Primary Protocol"
        assert first.json()["collaborator_account_ids"] == [str(COLLABORATOR_ID)]

        messages = client.get(
            f"/conversations/{state['first_id']}/messages?limit=2",
            headers=headers(OWNER_ID),
        )
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()["items"]] == ["user", "user"]
        assert messages.json()["next_cursor"] is not None
        remaining = client.get(
            f"/conversations/{state['first_id']}/messages",
            headers=headers(OWNER_ID),
            params={"cursor": messages.json()["next_cursor"], "limit": 2},
        )
        assert [item["role"] for item in remaining.json()["items"]] == ["assistant"]
        assert [
            item["content"]
            for item in messages.json()["items"] + remaining.json()["items"]
        ] == ["Owner context", "Collaborator context", "Assistant context"]

        continued = client.get(
            "/conversations",
            headers=headers(OWNER_ID),
            params={"cursor": state["conversation_cursor"], "limit": 1},
        )
        assert continued.status_code == 200
        assert continued.json()["items"][0]["id"] != state["first_page_id"]
        archived = client.get(
            "/conversations?archived=true",
            headers=headers(OWNER_ID),
        )
        assert {item["id"] for item in archived.json()["items"]} == {
            state["archived_id"]
        }
        assert client.get(
            f"/conversations/{state['first_id']}",
            headers=headers(COLLABORATOR_ID),
        ).status_code == 200

        asyncio.run(remove_collaborator_membership())
        assert client.get(
            f"/conversations/{state['first_id']}",
            headers=headers(COLLABORATOR_ID),
        ).status_code == 404
        owner_history = client.get(
            f"/conversations/{state['first_id']}/messages",
            headers=headers(OWNER_ID),
        )
        assert len(owner_history.json()["items"]) == 3
