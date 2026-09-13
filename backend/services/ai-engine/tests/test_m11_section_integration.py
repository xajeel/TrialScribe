"""Live ICH M11 section workspace checks driven by the isolated test script."""

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_ai.api.app import app

pytestmark = pytest.mark.integration

INTEGRATION_ENABLED = os.getenv("TRIALSCRIBE_AI_M11_INTEGRATION") == "1"
PHASE = os.getenv("TRIALSCRIBE_AI_M11_PHASE", "")
STATE_FILE = Path(os.getenv("TRIALSCRIBE_AI_M11_STATE_FILE", "/nonexistent"))

OWNER_ID = UUID("73000000-0000-4000-8000-000000000001")
COLLABORATOR_ID = UUID("73000000-0000-4000-8000-000000000002")
STRANGER_ID = UUID("73000000-0000-4000-8000-000000000003")
FOREIGN_ID = UUID("73000000-0000-4000-8000-000000000004")
ORGANIZATION_ID = UUID("73000000-0000-4000-8000-000000000005")
FOREIGN_ORGANIZATION_ID = UUID("73000000-0000-4000-8000-000000000006")


def require_phase(expected: str) -> None:
    if not INTEGRATION_ENABLED or PHASE != expected:
        pytest.skip(f"requires M11 section integration {expected} phase")


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
                (OWNER_ID, "m11-owner@example.com"),
                (COLLABORATOR_ID, "m11-collaborator@example.com"),
                (STRANGER_ID, "m11-stranger@example.com"),
                (FOREIGN_ID, "m11-foreign@example.com"),
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
                (ORGANIZATION_ID, "M11 Research"),
                (FOREIGN_ORGANIZATION_ID, "Foreign M11 Research"),
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


def revise(
    client: TestClient,
    conversation_id: str,
    section_number: str,
    expected_revision: int,
    *,
    instructions: str | None = None,
    content: str | None = None,
    account_id: UUID = OWNER_ID,
) -> dict[str, object]:
    body: dict[str, object] = {"expected_revision": expected_revision}
    if instructions is not None:
        body["instructions"] = instructions
    if content is not None:
        body["content"] = content
    response = client.patch(
        f"/conversations/{conversation_id}/m11-sections/{section_number}",
        headers=headers(account_id),
        json=body,
    )
    assert response.status_code == 200
    return response.json()


def transition(
    client: TestClient,
    conversation_id: str,
    section_number: str,
    action: str,
    expected_revision: int,
    *,
    account_id: UUID = OWNER_ID,
) -> dict[str, object]:
    response = client.post(
        f"/conversations/{conversation_id}/m11-sections/{section_number}/{action}",
        headers=headers(account_id),
        json={"expected_revision": expected_revision},
    )
    assert response.status_code == 200
    return response.json()


def test_prepare_ordered_workspace_and_section_states() -> None:
    require_phase("prepare")
    asyncio.run(seed_tenants())

    with TestClient(app) as client:
        created = client.post(
            "/conversations",
            headers=headers(OWNER_ID),
            json={"title": "M11 Protocol"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]
        shared = client.put(
            f"/conversations/{conversation_id}/collaborators",
            headers=headers(OWNER_ID),
            json={"account_ids": [str(COLLABORATOR_ID)]},
        )
        assert shared.status_code == 200

        initialized = client.put(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(OWNER_ID),
        )
        assert initialized.status_code == 200
        assert initialized.json()["catalog_version"] == "ICH_M11_STEP_4_2025_11_19"
        assert [item["section_number"] for item in initialized.json()["items"]] == [
            str(number) for number in range(1, 15)
        ]
        repeated = client.put(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(COLLABORATOR_ID),
        )
        assert repeated.json() == initialized.json()

        revised = revise(
            client,
            conversation_id,
            "2",
            0,
            instructions="Explain the scientific context.",
            content="Durable introduction draft.",
            account_id=COLLABORATOR_ID,
        )
        done_draft = revise(
            client,
            conversation_id,
            "3",
            0,
            content="Durable objectives draft.",
        )
        done = transition(
            client,
            conversation_id,
            "3",
            "done",
            int(done_draft["current_revision"]),
        )
        reopened_draft = revise(
            client,
            conversation_id,
            "4",
            0,
            content="Durable design draft.",
        )
        reopened_done = transition(
            client,
            conversation_id,
            "4",
            "done",
            int(reopened_draft["current_revision"]),
        )
        reopened = transition(
            client,
            conversation_id,
            "4",
            "reopen",
            int(reopened_done["current_revision"]),
            account_id=COLLABORATOR_ID,
        )

        assert client.get(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(STRANGER_ID),
        ).status_code == 404
        assert client.get(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(FOREIGN_ID, FOREIGN_ORGANIZATION_ID),
        ).status_code == 404

        STATE_FILE.write_text(
            json.dumps(
                {
                    "conversation_id": conversation_id,
                    "section_ids": {
                        item["section_number"]: item["id"]
                        for item in initialized.json()["items"][:4]
                    },
                    "revisions": {
                        "2": revised["current_revision"],
                        "3": done["current_revision"],
                        "4": reopened["current_revision"],
                    },
                }
            ),
            encoding="utf-8",
        )
        STATE_FILE.chmod(0o600)


def test_verify_section_state_history_and_continued_revision_after_restart() -> None:
    require_phase("verify")
    state: dict[str, object] = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    conversation_id = str(state["conversation_id"])

    with TestClient(app) as client:
        workspace = client.get(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(OWNER_ID),
        )
        assert workspace.status_code == 200
        items = workspace.json()["items"]
        assert len(items) == 14
        assert [item["section_number"] for item in items] == [
            str(number) for number in range(1, 15)
        ]
        assert [item["position"] for item in items] == list(range(1, 15))

        untouched, revised, done, reopened = items[:4]
        assert untouched["status"] == "draft"
        assert untouched["current_revision"] == 0
        assert untouched["instructions"] == ""
        assert untouched["content"] == ""
        assert revised["instructions"] == "Explain the scientific context."
        assert revised["content"] == "Durable introduction draft."
        assert revised["status"] == "draft"
        assert revised["current_revision"] == 1
        assert done["content"] == "Durable objectives draft."
        assert done["status"] == "done"
        assert done["current_revision"] == 2
        assert done["completed_at"] is not None
        assert done["completed_by_account_id"] == str(OWNER_ID)
        assert reopened["content"] == "Durable design draft."
        assert reopened["status"] == "draft"
        assert reopened["current_revision"] == 3
        assert reopened["completed_at"] is None
        assert reopened["completed_by_account_id"] is None

        expected_ids = state["section_ids"]
        assert isinstance(expected_ids, dict)
        assert {
            item["section_number"]: item["id"] for item in items[:4]
        } == expected_ids
        expected_revisions = state["revisions"]
        assert isinstance(expected_revisions, dict)
        assert {item["section_number"]: item["current_revision"] for item in items[1:4]} == (
            expected_revisions
        )

        expected_actions = {
            "1": [],
            "2": ["revised"],
            "3": ["revised", "done"],
            "4": ["revised", "done", "reopened"],
        }
        for section_number, actions in expected_actions.items():
            response = client.get(
                f"/conversations/{conversation_id}/m11-sections/"
                f"{section_number}/revisions?limit=20",
                headers=headers(OWNER_ID),
            )
            assert response.status_code == 200
            history = response.json()["items"]
            assert [item["action"] for item in history] == actions
            assert [item["revision_number"] for item in history] == list(
                range(1, len(actions) + 1)
            )
            assert all(item["organization_id"] == str(ORGANIZATION_ID) for item in history)
            assert all(item["conversation_id"] == conversation_id for item in history)
            if section_number == "4":
                assert [item["author_account_id"] for item in history] == [
                    str(OWNER_ID),
                    str(OWNER_ID),
                    str(COLLABORATOR_ID),
                ]

        continued = revise(
            client,
            conversation_id,
            "2",
            1,
            content="Continued after PostgreSQL restart.",
        )
        assert continued["current_revision"] == 2
        continued_history = client.get(
            f"/conversations/{conversation_id}/m11-sections/2/revisions?limit=1",
            headers=headers(OWNER_ID),
        )
        assert continued_history.json()["next_after_revision"] == 1
        second_page = client.get(
            f"/conversations/{conversation_id}/m11-sections/2/revisions"
            "?after_revision=1&limit=1",
            headers=headers(OWNER_ID),
        )
        assert second_page.json()["items"][0]["revision_number"] == 2
        assert second_page.json()["items"][0]["content"] == (
            "Continued after PostgreSQL restart."
        )

        assert client.get(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(STRANGER_ID),
        ).status_code == 404
        assert client.get(
            f"/conversations/{conversation_id}/m11-sections",
            headers=headers(FOREIGN_ID, FOREIGN_ORGANIZATION_ID),
        ).status_code == 404
