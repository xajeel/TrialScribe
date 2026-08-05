from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from trialscribe_user.api import routes
from trialscribe_user.api.app import app
from trialscribe_user.api.dependencies import (
    get_current_account_id,
    get_database_runtime,
    get_now,
    get_settings,
    get_token_verifier,
)
from trialscribe_user.models.invitation import Invitation
from trialscribe_user.models.membership import Membership, MembershipRole
from trialscribe_user.models.organization import Organization
from trialscribe_user.repositories.identities import OrganizationIdentity
from trialscribe_user.services.authorization import (
    OrganizationNotFoundError,
    PermissionDeniedError,
)
from trialscribe_user.services.invitations import InvitationConflictError
from trialscribe_user.services.organizations import MembershipConflictError

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000041")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000042")
TARGET_ID = UUID("00000000-0000-4000-8000-000000000043")
INVITATION_ID = UUID("00000000-0000-4000-8000-000000000044")

IDENTITIES = {
    ACCOUNT_ID: OrganizationIdentity(
        account_id=ACCOUNT_ID,
        email="owner@example.com",
        is_active=True,
    ),
    TARGET_ID: OrganizationIdentity(
        account_id=TARGET_ID,
        email="member@example.com",
        is_active=False,
    ),
}


class FakeDatabaseRuntime:
    @asynccontextmanager
    async def transaction(self) -> Any:
        yield object()


class FakeOrganizationService:
    def __init__(self) -> None:
        self.organization = Organization(id=ORGANIZATION_ID, name="Research Team")
        self.organization.created_at = NOW
        self.owner = self.membership(ACCOUNT_ID, MembershipRole.OWNER)
        self.member = self.membership(TARGET_ID, MembershipRole.MEMBER)

    @staticmethod
    def membership(account_id: UUID, role: MembershipRole) -> Membership:
        item = Membership(
            id=uuid4(),
            organization_id=ORGANIZATION_ID,
            account_id=account_id,
            role=role.value,
        )
        item.created_at = NOW
        return item

    async def create_organization(
        self,
        _account_id: UUID,
        name: str,
    ) -> tuple[Organization, Membership]:
        self.organization.name = name
        return self.organization, self.owner

    async def list_organizations(
        self,
        _account_id: UUID,
    ) -> list[tuple[Organization, Membership]]:
        return [(self.organization, self.owner)]

    async def get_organization(
        self,
        _account_id: UUID,
        organization_id: UUID,
    ) -> tuple[Organization, Membership]:
        if organization_id != ORGANIZATION_ID:
            raise OrganizationNotFoundError("hidden")
        return self.organization, self.owner

    async def list_members(
        self,
        _account_id: UUID,
        organization_id: UUID,
    ) -> list[Membership]:
        if organization_id != ORGANIZATION_ID:
            raise OrganizationNotFoundError("hidden")
        return [self.owner, self.member]

    async def change_role(
        self,
        _account_id: UUID,
        _organization_id: UUID,
        target_account_id: UUID,
        role: str,
    ) -> Membership:
        if target_account_id == ACCOUNT_ID:
            raise MembershipConflictError("Organization must retain at least one owner")
        self.member.role = role
        return self.member

    async def remove_member(
        self,
        _account_id: UUID,
        _organization_id: UUID,
        target_account_id: UUID,
    ) -> None:
        if target_account_id == ACCOUNT_ID:
            raise PermissionDeniedError("denied")


class FakeInvitationService:
    def __init__(self, organization_service: FakeOrganizationService) -> None:
        self.organization_service = organization_service
        self.invitation = Invitation(
            id=INVITATION_ID,
            organization_id=ORGANIZATION_ID,
            email="person@example.com",
            role=MembershipRole.MEMBER.value,
            invited_by_account_id=ACCOUNT_ID,
            token_hash="a" * 64,
            expires_at=NOW,
            accepted_at=None,
            revoked_at=None,
        )
        self.invitation.created_at = NOW

    async def create_invitation(self, *_args: object) -> tuple[Invitation, str]:
        return (
            self.invitation,
            "https://app.example.com/invitations/accept?token=secret",
        )

    async def list_invitations(self, *_args: object) -> list[Invitation]:
        return [self.invitation]

    async def revoke_invitation(self, *_args: object) -> Invitation:
        self.invitation.revoked_at = NOW
        return self.invitation

    async def accept_invitation(
        self,
        token: str,
        account_id: UUID,
        _now: datetime,
    ) -> Membership:
        if token == "duplicate":
            raise InvitationConflictError("Account already belongs to organization")
        return self.organization_service.membership(account_id, MembershipRole.MEMBER)


class FakeIdentityRepository:
    async def resolve(
        self,
        _organization_id: UUID,
        account_ids: list[UUID],
    ) -> dict[UUID, OrganizationIdentity]:
        return {item: IDENTITIES[item] for item in account_ids if item in IDENTITIES}


class FakeDirectoryService:
    async def resolve(
        self,
        _account_id: UUID,
        organization_id: UUID,
        account_ids: list[UUID],
    ) -> dict[UUID, OrganizationIdentity]:
        if organization_id != ORGANIZATION_ID:
            raise OrganizationNotFoundError("hidden")
        return {item: IDENTITIES[item] for item in account_ids if item in IDENTITIES}


@pytest.fixture
def api_context(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    organization_service = FakeOrganizationService()
    invitation_service = FakeInvitationService(organization_service)
    monkeypatch.setattr(
        routes, "OrganizationService", lambda *_args: organization_service
    )
    monkeypatch.setattr(routes, "InvitationService", lambda *_args: invitation_service)
    monkeypatch.setattr(routes, "IdentityRepository", lambda *_args: FakeIdentityRepository())
    monkeypatch.setattr(routes, "IdentityDirectoryService", lambda *_args: FakeDirectoryService())
    app.dependency_overrides[get_current_account_id] = lambda: ACCOUNT_ID
    app.dependency_overrides[get_database_runtime] = lambda: FakeDatabaseRuntime()
    app.dependency_overrides[get_settings] = lambda: object()
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        yield {
            "client": TestClient(app),
            "organization": organization_service,
            "invitation": invitation_service,
        }
    finally:
        app.dependency_overrides.clear()


def test_missing_bearer_token_is_generic_unauthorized() -> None:
    app.dependency_overrides[get_token_verifier] = lambda: object()
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        response = TestClient(app).get("/v1/organizations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_organization_free_then_create_list_and_read(
    api_context: dict[str, Any],
) -> None:
    client = api_context["client"]

    created = client.post("/v1/organizations", json={"name": "  Research Team  "})
    listed = client.get("/v1/organizations")
    fetched = client.get(f"/v1/organizations/{ORGANIZATION_ID}")
    members = client.get(f"/v1/organizations/{ORGANIZATION_ID}/members")

    assert created.status_code == 201
    assert created.json()["role"] == "owner"
    assert listed.json()[0]["id"] == str(ORGANIZATION_ID)
    assert fetched.json()["name"] == "Research Team"
    assert {item["role"] for item in members.json()} == {"owner", "member"}
    by_account = {item["account_id"]: item["identity"] for item in members.json()}
    assert by_account[str(ACCOUNT_ID)]["email"] == "owner@example.com"
    assert by_account[str(TARGET_ID)] == {
        "account_id": str(TARGET_ID),
        "email": "member@example.com",
        "is_active": False,
    }


def test_membership_updates_and_errors_are_stable(api_context: dict[str, Any]) -> None:
    client = api_context["client"]
    changed = client.patch(
        f"/v1/organizations/{ORGANIZATION_ID}/members/{TARGET_ID}",
        json={"role": "admin"},
    )
    hidden = client.get(f"/v1/organizations/{uuid4()}")
    forbidden = client.delete(
        f"/v1/organizations/{ORGANIZATION_ID}/members/{ACCOUNT_ID}"
    )
    conflict = client.patch(
        f"/v1/organizations/{ORGANIZATION_ID}/members/{ACCOUNT_ID}",
        json={"role": "member"},
    )

    assert changed.json()["role"] == "admin"
    assert changed.json()["identity"]["email"] == "member@example.com"
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "Organization not found"}
    assert forbidden.status_code == 403
    assert conflict.status_code == 409


def test_invitation_routes_return_secret_only_on_creation(
    api_context: dict[str, Any],
) -> None:
    client = api_context["client"]
    created = client.post(
        f"/v1/organizations/{ORGANIZATION_ID}/invitations",
        json={"email": "person@example.com", "role": "member"},
    )
    listed = client.get(f"/v1/organizations/{ORGANIZATION_ID}/invitations")
    accepted = client.post(
        "/v1/organization-invitations/accept",
        json={"token": "single-use-secret"},
    )
    revoked = client.delete(
        f"/v1/organizations/{ORGANIZATION_ID}/invitations/{INVITATION_ID}"
    )

    assert created.status_code == 201
    assert "token=secret" in created.json()["accept_url"]
    assert "accept_url" not in listed.json()[0]
    assert "token_hash" not in listed.text
    assert created.json()["invited_by"]["email"] == "owner@example.com"
    assert listed.json()[0]["invited_by"] == created.json()["invited_by"]
    assert accepted.json()["account_id"] == str(ACCOUNT_ID)
    assert accepted.json()["identity"]["email"] == "owner@example.com"
    assert revoked.status_code == 204


def test_service_exception_text_is_not_returned(api_context: dict[str, Any]) -> None:
    response = api_context["client"].post(
        "/v1/organization-invitations/accept",
        json={"token": "duplicate"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Invitation conflicts with organization state"}
    assert "already belongs" not in response.text


def test_validation_never_echoes_invitation_secret(api_context: dict[str, Any]) -> None:
    client = api_context["client"]
    secret = "very-sensitive-invitation-token" + ("x" * 600)

    response = client.post(
        "/v1/organization-invitations/accept",
        json={"token": secret},
    )
    invalid_role = client.post(
        f"/v1/organizations/{ORGANIZATION_ID}/invitations",
        json={"email": "person@example.com", "role": "owner"},
    )

    assert response.status_code == 422
    assert secret not in response.text
    assert "input" not in response.text
    assert invalid_role.status_code == 422
    assert "input" not in invalid_role.text


def test_identity_resolution_is_bounded_and_omits_unknown_accounts(
    api_context: dict[str, Any],
) -> None:
    client = api_context["client"]
    unknown = uuid4()

    resolved = client.post(
        f"/v1/organizations/{ORGANIZATION_ID}/identity-summaries/resolve",
        json={"account_ids": [str(TARGET_ID), str(unknown)]},
    )
    duplicate = client.post(
        f"/v1/organizations/{ORGANIZATION_ID}/identity-summaries/resolve",
        json={"account_ids": [str(TARGET_ID), str(TARGET_ID)]},
    )
    oversized = client.post(
        f"/v1/organizations/{ORGANIZATION_ID}/identity-summaries/resolve",
        json={"account_ids": [str(UUID(int=value)) for value in range(1, 102)]},
    )
    foreign = client.post(
        f"/v1/organizations/{uuid4()}/identity-summaries/resolve",
        json={"account_ids": [str(TARGET_ID)]},
    )

    assert resolved.status_code == 200
    assert resolved.json() == [
        {
            "account_id": str(TARGET_ID),
            "email": "member@example.com",
            "is_active": False,
        }
    ]
    assert duplicate.status_code == 422
    assert oversized.status_code == 422
    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "Organization not found"}
