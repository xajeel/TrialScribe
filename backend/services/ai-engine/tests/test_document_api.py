from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from trialscribe_ai.api import documents as routes
from trialscribe_ai.api.app import app
from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
)
from trialscribe_ai.models.document import Document
from trialscribe_ai.utils.exceptions import (
    DocumentNotFoundError,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidTrialDataError,
    UnsupportedDocumentTypeError,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("41000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("41000000-0000-4000-8000-000000000002")
CONVERSATION_ID = UUID("41000000-0000-4000-8000-000000000003")
DOCUMENT_ID = UUID("41000000-0000-4000-8000-000000000004")


class FakeDatabaseRuntime:
    @asynccontextmanager
    async def transaction(self) -> Any:
        yield object()


class FakeDocumentService:
    def __init__(self) -> None:
        self.document = Document(
            id=DOCUMENT_ID,
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            uploaded_by_account_id=ACCOUNT_ID,
            kind="research_document",
            filename="paper.pdf",
            content_type="application/pdf",
            byte_size=8,
            status="pending",
            error=None,
            content=b"%PDF-1.7",
            created_at=NOW,
            updated_at=NOW,
        )
        self.error: Exception | None = None

    async def upload(self, *_args: object) -> Document:
        if self.error is not None:
            raise self.error
        return self.document

    async def list(
        self, *_args: object, **_kwargs: object
    ) -> tuple[list[Document], str | None]:
        return [self.document], "next-document"

    async def get(self, *_args: object) -> Document:
        return self.document

    async def delete(self, *_args: object) -> None:
        return None


@pytest.fixture
def api_context(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, FakeDocumentService]:
    service = FakeDocumentService()
    monkeypatch.setattr(routes, "DocumentService", lambda *_args: service)
    app.dependency_overrides[get_current_account_id] = lambda: ACCOUNT_ID
    app.dependency_overrides[get_current_organization_id] = lambda: ORGANIZATION_ID
    app.dependency_overrides[get_database_runtime] = lambda: FakeDatabaseRuntime()
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        yield TestClient(app), service
    finally:
        app.dependency_overrides.clear()


def test_upload_returns_created_document(
    api_context: tuple[TestClient, FakeDocumentService],
) -> None:
    client, _ = api_context

    response = client.post(
        f"/conversations/{CONVERSATION_ID}/documents",
        data={"kind": "research_document"},
        files={"file": ("paper.pdf", b"%PDF-1.7 body", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organization_id"] == str(ORGANIZATION_ID)
    assert body["kind"] == "research_document"
    assert body["status"] == "pending"
    assert "content" not in body


def test_list_get_content_and_delete(
    api_context: tuple[TestClient, FakeDocumentService],
) -> None:
    client, _ = api_context

    listed = client.get(f"/conversations/{CONVERSATION_ID}/documents?limit=20")
    fetched = client.get(f"/conversations/{CONVERSATION_ID}/documents/{DOCUMENT_ID}")
    content = client.get(
        f"/conversations/{CONVERSATION_ID}/documents/{DOCUMENT_ID}/content"
    )
    deleted = client.delete(f"/conversations/{CONVERSATION_ID}/documents/{DOCUMENT_ID}")

    assert listed.json()["next_cursor"] == "next-document"
    assert fetched.json()["id"] == str(DOCUMENT_ID)
    assert content.status_code == 200
    assert content.content == b"%PDF-1.7"
    assert content.headers["content-type"].startswith("application/pdf")
    assert "paper.pdf" in content.headers["content-disposition"]
    assert deleted.status_code == 204


def test_invalid_kind_is_rejected(
    api_context: tuple[TestClient, FakeDocumentService],
) -> None:
    client, _ = api_context

    response = client.post(
        f"/conversations/{CONVERSATION_ID}/documents",
        data={"kind": "bogus"},
        files={"file": ("f.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            DocumentTooLargeError("postgresql://secret"),
            413,
            "Document exceeds the maximum allowed size",
        ),
        (
            UnsupportedDocumentTypeError("private detail"),
            415,
            "Unsupported document type",
        ),
        (
            InvalidTrialDataError("private detail"),
            422,
            "Trial data must be a JSON object",
        ),
        (EmptyDocumentError("private detail"), 422, "Uploaded document is empty"),
        (DocumentNotFoundError("private detail"), 404, "Document not found"),
    ],
)
def test_upload_errors_are_allow_listed(
    api_context: tuple[TestClient, FakeDocumentService],
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    client, service = api_context
    service.error = error

    response = client.post(
        f"/conversations/{CONVERSATION_ID}/documents",
        data={"kind": "trial_data"},
        files={"file": ("trial.json", b"{}", "application/json")},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert str(error) not in response.text


def test_trusted_headers_are_required_for_documents() -> None:
    client = TestClient(app)

    missing = client.get(f"/conversations/{CONVERSATION_ID}/documents")
    malformed_account = client.get(
        f"/conversations/{CONVERSATION_ID}/documents",
        headers={
            "X-TrialScribe-Account-ID": "secret-not-a-uuid",
            "X-TrialScribe-Organization-ID": str(ORGANIZATION_ID),
        },
    )

    assert missing.status_code in {401, 422}
    assert malformed_account.status_code == 422
    assert malformed_account.json() == {"detail": "Invalid account context"}
    assert "secret-not-a-uuid" not in malformed_account.text
