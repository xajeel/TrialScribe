"""Live document ingestion checks driven by the isolated test script."""

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

INTEGRATION_ENABLED = os.getenv("TRIALSCRIBE_AI_DOCUMENT_INTEGRATION") == "1"
PHASE = os.getenv("TRIALSCRIBE_AI_DOCUMENT_PHASE", "")
STATE_FILE = Path(os.getenv("TRIALSCRIBE_AI_DOCUMENT_STATE_FILE", "/nonexistent"))

OWNER_ID = UUID("51000000-0000-4000-8000-000000000001")
FOREIGN_ID = UUID("51000000-0000-4000-8000-000000000002")
ORGANIZATION_ID = UUID("51000000-0000-4000-8000-000000000003")
FOREIGN_ORGANIZATION_ID = UUID("51000000-0000-4000-8000-000000000004")

TRIAL_BYTES = b'{"nct": "NCT-INTEGRATION"}'
PDF_BYTES = b"%PDF-1.7\nintegration evidence\n"


def require_phase(expected: str) -> None:
    if not INTEGRATION_ENABLED or PHASE != expected:
        pytest.skip(f"requires document integration {expected} phase")


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
                (OWNER_ID, "document-owner@example.com"),
                (FOREIGN_ID, "document-foreign@example.com"),
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
                (ORGANIZATION_ID, "Document Research"),
                (FOREIGN_ORGANIZATION_ID, "Foreign Research"),
            ):
                await session.execute(
                    text(
                        "INSERT INTO trialscribe.organizations (id, name) "
                        "VALUES (:id, :name)"
                    ),
                    {"id": organization_id, "name": name},
                )
            for organization_id, account_id in (
                (ORGANIZATION_ID, OWNER_ID),
                (FOREIGN_ORGANIZATION_ID, FOREIGN_ID),
            ):
                await session.execute(
                    text(
                        "INSERT INTO trialscribe.organization_memberships "
                        "(id, organization_id, account_id, role) "
                        "VALUES (:id, :organization_id, :account_id, 'owner')"
                    ),
                    {
                        "id": uuid4(),
                        "organization_id": organization_id,
                        "account_id": account_id,
                    },
                )
    finally:
        await runtime.dispose()


def test_prepare_uploads_documents() -> None:
    require_phase("prepare")
    asyncio.run(seed_tenants())

    with TestClient(app) as client:
        conversation = client.post(
            "/conversations",
            headers=headers(OWNER_ID),
            json={"title": "Evidence Protocol"},
        )
        assert conversation.status_code == 201
        conversation_id = conversation.json()["id"]

        trial = client.post(
            f"/conversations/{conversation_id}/documents",
            headers=headers(OWNER_ID),
            data={"kind": "trial_data"},
            files={"file": ("trial.json", TRIAL_BYTES, "application/json")},
        )
        assert trial.status_code == 201
        assert trial.json()["content_type"] == "application/json"

        pdf = client.post(
            f"/conversations/{conversation_id}/documents",
            headers=headers(OWNER_ID),
            data={"kind": "research_document"},
            files={"file": ("evidence.pdf", PDF_BYTES, "application/pdf")},
        )
        assert pdf.status_code == 201

        assert client.get(
            f"/conversations/{conversation_id}/documents/{pdf.json()['id']}",
            headers=headers(FOREIGN_ID, FOREIGN_ORGANIZATION_ID),
        ).status_code == 404

        state = {
            "conversation_id": conversation_id,
            "trial_id": trial.json()["id"],
            "pdf_id": pdf.json()["id"],
        }
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        STATE_FILE.chmod(0o600)


def test_verify_documents_persist_and_stay_scoped() -> None:
    require_phase("verify")
    state: dict[str, str] = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    conversation_id = state["conversation_id"]

    with TestClient(app) as client:
        metadata = client.get(
            f"/conversations/{conversation_id}/documents/{state['pdf_id']}",
            headers=headers(OWNER_ID),
        )
        assert metadata.status_code == 200
        assert metadata.json()["filename"] == "evidence.pdf"
        assert metadata.json()["byte_size"] == len(PDF_BYTES)

        content = client.get(
            f"/conversations/{conversation_id}/documents/{state['pdf_id']}/content",
            headers=headers(OWNER_ID),
        )
        assert content.status_code == 200
        assert content.content == PDF_BYTES

        listed = client.get(
            f"/conversations/{conversation_id}/documents",
            headers=headers(OWNER_ID),
        )
        assert {item["id"] for item in listed.json()["items"]} == {
            state["trial_id"],
            state["pdf_id"],
        }

        assert client.get(
            f"/conversations/{conversation_id}/documents/{state['pdf_id']}",
            headers=headers(FOREIGN_ID, FOREIGN_ORGANIZATION_ID),
        ).status_code == 404
