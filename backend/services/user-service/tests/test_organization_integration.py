"""Live organization lifecycle checks driven by the isolated test script."""

import asyncio
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_user.api.app import app
from trialscribe_user.config import UserSettings
from trialscribe_user.security.tokens import AccessTokenVerifier

pytestmark = pytest.mark.integration

INTEGRATION_ENABLED = os.getenv("TRIALSCRIBE_USER_INTEGRATION") == "1"
PHASE = os.getenv("TRIALSCRIBE_USER_PHASE", "")
STATE_FILE = Path(os.getenv("TRIALSCRIBE_USER_STATE_FILE", "/nonexistent"))
PRIVATE_KEY_B64 = os.getenv("TRIALSCRIBE_USER_TEST_PRIVATE_KEY_B64", "")

OWNER_ID = UUID("10000000-0000-4000-8000-000000000001")
ADMIN_ID = UUID("10000000-0000-4000-8000-000000000002")
MEMBER_ID = UUID("10000000-0000-4000-8000-000000000003")
NEW_ACCOUNT_ID = UUID("10000000-0000-4000-8000-000000000004")
REPLAY_ID = UUID("10000000-0000-4000-8000-000000000005")
REVOKED_ID = UUID("10000000-0000-4000-8000-000000000006")
EXPIRED_ID = UUID("10000000-0000-4000-8000-000000000007")
FOREIGN_ID = UUID("10000000-0000-4000-8000-000000000008")
EMAILS = {
    OWNER_ID: "owner@example.com",
    ADMIN_ID: "admin@example.com",
    MEMBER_ID: "member@example.com",
    NEW_ACCOUNT_ID: "new@example.com",
    REPLAY_ID: "replay@example.com",
    REVOKED_ID: "revoked@example.com",
    EXPIRED_ID: "expired@example.com",
    FOREIGN_ID: "foreign@example.com",
}


def require_phase(expected: str) -> None:
    if not INTEGRATION_ENABLED or PHASE != expected:
        pytest.skip(f"requires organization integration {expected} phase")


def access_token(account_id: UUID) -> str:
    now = datetime.now(UTC)
    private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(PRIVATE_KEY_B64, validate=True)
    )
    settings = UserSettings()
    return jwt.encode(
        {
            "sub": str(account_id),
            "iss": settings.auth_jwt_issuer,
            "aud": settings.auth_jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=15),
            "jti": str(uuid4()),
            "type": "access",
        },
        private_key,
        algorithm="EdDSA",
    )


def headers(account_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token(account_id)}"}


async def insert_accounts(account_ids: list[UUID]) -> None:
    runtime = create_database_runtime(DatabaseSettings())
    try:
        async with runtime.transaction() as session:
            for account_id in account_ids:
                await session.execute(
                    text(
                        "INSERT INTO trialscribe.accounts "
                        "(id, email, password_hash, is_active) "
                        "VALUES (:id, :email, :password_hash, true) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": account_id,
                        "email": EMAILS[account_id],
                        "password_hash": "integration-fixture-not-for-login",
                    },
                )
    finally:
        await runtime.dispose()


async def expire_invitation(invitation_id: UUID) -> None:
    runtime = create_database_runtime(DatabaseSettings())
    try:
        async with runtime.transaction() as session:
            await session.execute(
                text(
                    "UPDATE trialscribe.organization_invitations "
                    "SET expires_at = :expires_at WHERE id = :id"
                ),
                {"id": invitation_id, "expires_at": datetime.now(UTC) - timedelta(seconds=1)},
            )
    finally:
        await runtime.dispose()


def invitation_token(response: Any) -> str:
    assert response.status_code == 201
    return parse_qs(urlsplit(response.json()["accept_url"]).query)["token"][0]


def create_invitation(
    client: TestClient,
    organization_id: str,
    actor_id: UUID,
    invited_id: UUID,
    role: str = "member",
) -> Any:
    return client.post(
        f"/v1/organizations/{organization_id}/invitations",
        headers=headers(actor_id),
        json={"email": EMAILS[invited_id], "role": role},
    )


def accept_invitation(client: TestClient, account_id: UUID, token: str) -> Any:
    return client.post(
        "/v1/organization-invitations/accept",
        headers=headers(account_id),
        json={"token": token},
    )


def resolve_identities(
    client: TestClient,
    organization_id: str,
    actor_id: UUID,
    account_ids: list[UUID],
) -> Any:
    return client.post(
        f"/v1/organizations/{organization_id}/identity-summaries/resolve",
        headers=headers(actor_id),
        json={"account_ids": [str(account_id) for account_id in account_ids]},
    )


def test_prepare_complete_organization_lifecycle() -> None:
    require_phase("prepare")
    assert "auth_jwt_private_key_b64" not in UserSettings.model_fields
    assert not hasattr(AccessTokenVerifier(UserSettings()), "issue_access_token")
    asyncio.run(
        insert_accounts(
            [
                OWNER_ID,
                ADMIN_ID,
                MEMBER_ID,
                REPLAY_ID,
                REVOKED_ID,
                EXPIRED_ID,
                FOREIGN_ID,
            ]
        )
    )

    with TestClient(app) as client:
        empty = client.get("/v1/organizations", headers=headers(OWNER_ID))
        assert empty.status_code == 200
        assert empty.json() == []

        created = client.post(
            "/v1/organizations",
            headers=headers(OWNER_ID),
            json={"name": "Primary Research"},
        )
        assert created.status_code == 201
        assert created.json()["role"] == "owner"
        organization_id = created.json()["id"]
        second = client.post(
            "/v1/organizations",
            headers=headers(OWNER_ID),
            json={"name": "Second Research"},
        )
        assert second.status_code == 201
        assert len(client.get("/v1/organizations", headers=headers(OWNER_ID)).json()) == 2
        foreign = client.post(
            "/v1/organizations",
            headers=headers(FOREIGN_ID),
            json={"name": "Foreign Research"},
        )
        assert foreign.status_code == 201

        admin_invite = create_invitation(
            client,
            organization_id,
            OWNER_ID,
            ADMIN_ID,
            "admin",
        )
        admin_token = invitation_token(admin_invite)
        assert admin_invite.json()["invited_by"] == {
            "account_id": str(OWNER_ID),
            "email": EMAILS[OWNER_ID],
            "is_active": True,
        }
        assert accept_invitation(client, ADMIN_ID, admin_token).json()["role"] == "admin"

        member_token = invitation_token(
            create_invitation(client, organization_id, ADMIN_ID, MEMBER_ID)
        )
        assert accept_invitation(client, MEMBER_ID, member_token).status_code == 200
        denied_admin = create_invitation(
            client,
            organization_id,
            ADMIN_ID,
            REPLAY_ID,
            "admin",
        )
        assert denied_admin.status_code == 403
        assert client.get(
            f"/v1/organizations/{organization_id}", headers=headers(MEMBER_ID)
        ).status_code == 200
        assert create_invitation(
            client,
            organization_id,
            MEMBER_ID,
            REPLAY_ID,
        ).status_code == 403
        assert client.get(
            f"/v1/organizations/{second.json()['id']}", headers=headers(MEMBER_ID)
        ).status_code == 404
        assert resolve_identities(
            client,
            second.json()["id"],
            MEMBER_ID,
            [OWNER_ID],
        ).status_code == 404

        members = client.get(
            f"/v1/organizations/{organization_id}/members",
            headers=headers(MEMBER_ID),
        )
        assert members.status_code == 200
        member_identities = {
            item["account_id"]: item["identity"] for item in members.json()
        }
        assert member_identities[str(OWNER_ID)]["email"] == EMAILS[OWNER_ID]
        assert member_identities[str(ADMIN_ID)]["email"] == EMAILS[ADMIN_ID]
        assert member_identities[str(MEMBER_ID)]["email"] == EMAILS[MEMBER_ID]
        assert all(identity["is_active"] for identity in member_identities.values())
        assert "password" not in json.dumps(members.json()).lower()

        invitation_history = client.get(
            f"/v1/organizations/{organization_id}/invitations",
            headers=headers(ADMIN_ID),
        )
        assert invitation_history.status_code == 200
        assert all("invited_by" in item for item in invitation_history.json())
        serialized_history = json.dumps(invitation_history.json()).lower()
        assert "accept_url" not in serialized_history
        assert "token" not in serialized_history

        mixed = resolve_identities(
            client,
            organization_id,
            OWNER_ID,
            [OWNER_ID, FOREIGN_ID, uuid4()],
        )
        assert mixed.status_code == 200
        assert mixed.json() == [
            {
                "account_id": str(OWNER_ID),
                "email": EMAILS[OWNER_ID],
                "is_active": True,
            }
        ]

        new_token = invitation_token(
            create_invitation(client, organization_id, OWNER_ID, NEW_ACCOUNT_ID)
        )
        asyncio.run(insert_accounts([NEW_ACCOUNT_ID]))
        assert accept_invitation(client, NEW_ACCOUNT_ID, new_token).status_code == 200
        promoted = client.patch(
            f"/v1/organizations/{organization_id}/members/{NEW_ACCOUNT_ID}",
            headers=headers(OWNER_ID),
            json={"role": "admin"},
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "admin"

        removed = client.delete(
            f"/v1/organizations/{organization_id}/members/{MEMBER_ID}",
            headers=headers(ADMIN_ID),
        )
        assert removed.status_code == 204
        remaining_members = client.get(
            f"/v1/organizations/{organization_id}/members",
            headers=headers(OWNER_ID),
        )
        assert remaining_members.status_code == 200
        assert str(MEMBER_ID) not in {
            item["account_id"] for item in remaining_members.json()
        }
        historical_member = resolve_identities(
            client,
            organization_id,
            OWNER_ID,
            [MEMBER_ID],
        )
        assert historical_member.status_code == 200
        assert historical_member.json() == [
            {
                "account_id": str(MEMBER_ID),
                "email": EMAILS[MEMBER_ID],
                "is_active": True,
            }
        ]
        assert client.get(
            f"/v1/organizations/{organization_id}", headers=headers(MEMBER_ID)
        ).status_code == 404
        assert client.patch(
            f"/v1/organizations/{organization_id}/members/{OWNER_ID}",
            headers=headers(OWNER_ID),
            json={"role": "member"},
        ).status_code == 409

        expired_response = create_invitation(
            client,
            organization_id,
            OWNER_ID,
            EXPIRED_ID,
        )
        expired_token = invitation_token(expired_response)
        asyncio.run(expire_invitation(UUID(expired_response.json()["id"])))
        assert accept_invitation(client, EXPIRED_ID, expired_token).status_code == 422

        revoked_response = create_invitation(
            client,
            organization_id,
            OWNER_ID,
            REVOKED_ID,
        )
        revoked_token = invitation_token(revoked_response)
        assert client.delete(
            f"/v1/organizations/{organization_id}/invitations/"
            f"{revoked_response.json()['id']}",
            headers=headers(OWNER_ID),
        ).status_code == 204
        assert accept_invitation(client, REVOKED_ID, revoked_token).status_code == 422

        replay_token = invitation_token(
            create_invitation(client, organization_id, OWNER_ID, REPLAY_ID)
        )
        assert accept_invitation(client, REPLAY_ID, replay_token).status_code == 200
        assert accept_invitation(client, REPLAY_ID, replay_token).status_code == 422

        state = {
            "organization_id": organization_id,
            "second_organization_id": second.json()["id"],
            "owner_token": access_token(OWNER_ID),
            "admin_token": access_token(ADMIN_ID),
        }
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        STATE_FILE.chmod(0o600)


def test_verify_persistence_after_postgres_restart() -> None:
    require_phase("verify")
    state: dict[str, str] = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    owner_headers = {"Authorization": f"Bearer {state['owner_token']}"}
    admin_headers = {"Authorization": f"Bearer {state['admin_token']}"}

    with TestClient(app) as client:
        organizations = client.get("/v1/organizations", headers=owner_headers)
        assert organizations.status_code == 200
        assert {item["id"] for item in organizations.json()} == {
            state["organization_id"],
            state["second_organization_id"],
        }
        members = client.get(
            f"/v1/organizations/{state['organization_id']}/members",
            headers=owner_headers,
        )
        assert members.status_code == 200
        roles = {item["account_id"]: item["role"] for item in members.json()}
        assert roles[str(OWNER_ID)] == "owner"
        assert roles[str(ADMIN_ID)] == "admin"
        assert str(MEMBER_ID) not in roles
        identities = {
            item["account_id"]: item["identity"] for item in members.json()
        }
        assert identities[str(OWNER_ID)]["email"] == EMAILS[OWNER_ID]
        assert identities[str(ADMIN_ID)]["email"] == EMAILS[ADMIN_ID]
        persisted_history = client.post(
            f"/v1/organizations/{state['organization_id']}"
            "/identity-summaries/resolve",
            headers=owner_headers,
            json={"account_ids": [str(MEMBER_ID), str(FOREIGN_ID)]},
        )
        assert persisted_history.status_code == 200
        assert persisted_history.json() == [
            {
                "account_id": str(MEMBER_ID),
                "email": EMAILS[MEMBER_ID],
                "is_active": True,
            }
        ]
        assert client.get(
            f"/v1/organizations/{state['organization_id']}",
            headers=admin_headers,
        ).status_code == 200
