from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from trialscribe_ai.api import m11_sections as routes
from trialscribe_ai.api.app import app
from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
)
from trialscribe_ai.models.m11_section import M11Section
from trialscribe_ai.models.m11_section_revision import M11SectionRevision
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    InvalidM11SectionInputError,
    M11SectionNotFoundError,
    M11SectionRevisionConflictError,
    M11SectionTransitionError,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("72000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("72000000-0000-4000-8000-000000000002")
CONVERSATION_ID = UUID("72000000-0000-4000-8000-000000000003")
SECTION_ID = UUID("72000000-0000-4000-8000-000000000004")
REVISION_ID = UUID("72000000-0000-4000-8000-000000000005")


class FakeDatabaseRuntime:
    def __init__(self) -> None:
        self.transactions = 0

    @asynccontextmanager
    async def transaction(self) -> Any:
        self.transactions += 1
        yield object()


class FakeM11SectionService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.initialize_calls = 0
        self.section = M11Section(
            id=SECTION_ID,
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            catalog_version="ICH_M11_STEP_4_2025_11_19",
            section_number="1",
            title="PROTOCOL SUMMARY",
            position=1,
            instructions="",
            content="Draft",
            status="draft",
            current_revision=0,
            completed_at=None,
            completed_by_account_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.revision = M11SectionRevision(
            id=REVISION_ID,
            section_id=SECTION_ID,
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            revision_number=1,
            action="revised",
            instructions="Use plain language.",
            content="Draft",
            status="draft",
            author_account_id=ACCOUNT_ID,
            created_at=NOW,
            updated_at=NOW,
        )

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    async def initialize_workspace(self, *_args: object) -> list[M11Section]:
        self._raise()
        self.initialize_calls += 1
        return [self.section]

    async def list_sections(self, *_args: object) -> list[M11Section]:
        self._raise()
        return [self.section]

    async def get_section(self, *_args: object) -> M11Section:
        self._raise()
        return self.section

    async def revise_section(
        self,
        *_args: object,
        expected_revision: int,
        instructions: str | None,
        content: str | None,
        now: datetime,
    ) -> M11Section:
        self._raise()
        assert expected_revision == self.section.current_revision
        assert now == NOW
        if instructions is not None:
            self.section.instructions = instructions
        if content is not None:
            self.section.content = content
        self.section.current_revision += 1
        return self.section

    async def mark_done(
        self,
        *_args: object,
        expected_revision: int,
        now: datetime,
    ) -> M11Section:
        self._raise()
        assert expected_revision == self.section.current_revision
        self.section.status = "done"
        self.section.completed_at = now
        self.section.completed_by_account_id = ACCOUNT_ID
        self.section.current_revision += 1
        return self.section

    async def reopen(
        self,
        *_args: object,
        expected_revision: int,
        now: datetime,
    ) -> M11Section:
        self._raise()
        assert expected_revision == self.section.current_revision
        self.section.status = "draft"
        self.section.completed_at = None
        self.section.completed_by_account_id = None
        self.section.current_revision += 1
        return self.section

    async def list_revisions(
        self,
        *_args: object,
        after_revision: int,
        limit: int,
    ) -> tuple[list[M11SectionRevision], int | None]:
        self._raise()
        assert after_revision == 0
        assert limit == 1
        return [self.revision], 1


@pytest.fixture
def api_context(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime]:
    service = FakeM11SectionService()
    runtime = FakeDatabaseRuntime()
    monkeypatch.setattr(routes, "M11SectionService", lambda *_args: service)
    app.dependency_overrides[get_current_account_id] = lambda: ACCOUNT_ID
    app.dependency_overrides[get_current_organization_id] = lambda: ORGANIZATION_ID
    app.dependency_overrides[get_database_runtime] = lambda: runtime
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        yield TestClient(app), service, runtime
    finally:
        app.dependency_overrides.clear()


def test_catalog_is_exact_versioned_ordered_and_public() -> None:
    response = TestClient(app).get("/m11/sections/catalog")

    assert response.status_code == 200
    assert response.json()["version"] == "ICH_M11_STEP_4_2025_11_19"
    assert [item["number"] for item in response.json()["items"]] == [
        str(number) for number in range(1, 15)
    ]
    assert response.json()["items"][0]["title"] == "PROTOCOL SUMMARY"
    assert response.json()["items"][-1]["title"] == "APPENDIX: REFERENCES"


def test_workspace_paths_are_scoped_transactional_and_initialization_is_idempotent(
    api_context: tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime],
) -> None:
    client, service, runtime = api_context
    root = f"/conversations/{CONVERSATION_ID}/m11-sections"

    first = client.put(root)
    second = client.put(root)
    listed = client.get(root)
    fetched = client.get(f"{root}/1")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert service.initialize_calls == 2
    assert listed.json()["catalog_version"] == "ICH_M11_STEP_4_2025_11_19"
    assert listed.json()["items"][0]["section_number"] == "1"
    assert fetched.json()["id"] == str(SECTION_ID)
    assert runtime.transactions == 4


def test_workspace_reports_its_persisted_catalog_version(
    api_context: tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime],
) -> None:
    client, service, _ = api_context
    service.section.catalog_version = "ICH_M11_STEP_4_PREVIOUS"

    response = client.get(f"/conversations/{CONVERSATION_ID}/m11-sections")

    assert response.status_code == 200
    assert response.json()["catalog_version"] == "ICH_M11_STEP_4_PREVIOUS"


def test_workspace_rejects_inconsistent_persisted_catalog_versions(
    api_context: tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime],
) -> None:
    section = routes._section_response(api_context[1].section)
    inconsistent = section.model_copy(
        update={
            "catalog_version": "ICH_M11_STEP_4_DIFFERENT",
            "section_number": "2",
            "position": 2,
        }
    )

    with pytest.raises(M11SectionTransitionError):
        routes._workspace_response([section, inconsistent])


def test_revise_done_reopen_and_revision_page_contracts(
    api_context: tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime],
) -> None:
    client, _, runtime = api_context
    root = f"/conversations/{CONVERSATION_ID}/m11-sections/1"

    revised = client.patch(
        root,
        json={
            "expected_revision": 0,
            "instructions": " Use plain language. ",
            "content": " Revised draft. ",
        },
    )
    done = client.post(f"{root}/done", json={"expected_revision": 1})
    reopened = client.post(f"{root}/reopen", json={"expected_revision": 2})
    history = client.get(f"{root}/revisions?after_revision=0&limit=1")

    assert revised.status_code == 200
    assert revised.json()["instructions"] == "Use plain language."
    assert revised.json()["content"] == "Revised draft."
    assert done.json()["status"] == "done"
    assert done.json()["completed_by_account_id"] == str(ACCOUNT_ID)
    assert reopened.json()["status"] == "draft"
    assert reopened.json()["completed_at"] is None
    assert history.json()["items"][0]["action"] == "revised"
    assert history.json()["next_after_revision"] == 1
    assert runtime.transactions == 4


def test_scoped_routes_require_trusted_context() -> None:
    response = TestClient(app).get(
        f"/conversations/{CONVERSATION_ID}/m11-sections"
    )

    assert response.status_code in {401, 422}


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (ConversationNotFoundError("tenant secret"), 404, "Conversation not found"),
        (M11SectionNotFoundError("section secret"), 404, "M11 section not found"),
        (ConversationArchivedError("archive secret"), 409, "Conversation is archived"),
        (
            M11SectionRevisionConflictError("revision secret"),
            409,
            "M11 section revision conflict",
        ),
        (
            M11SectionTransitionError("transition secret"),
            409,
            "M11 section transition is not allowed",
        ),
        (
            InvalidM11SectionInputError("input secret"),
            422,
            "Invalid M11 section input",
        ),
    ],
)
def test_service_and_tenant_errors_are_allow_listed(
    api_context: tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime],
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    client, service, _ = api_context
    service.error = error

    response = client.get(f"/conversations/{CONVERSATION_ID}/m11-sections")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert str(error) not in response.text


def test_validation_never_echoes_section_content(
    api_context: tuple[TestClient, FakeM11SectionService, FakeDatabaseRuntime],
) -> None:
    secret = "sensitive-section-content-" + ("x" * 200_100)

    response = api_context[0].patch(
        f"/conversations/{CONVERSATION_ID}/m11-sections/1",
        json={"expected_revision": 0, "content": secret},
    )

    assert response.status_code == 422
    assert secret not in response.text
    assert "input" not in response.text
