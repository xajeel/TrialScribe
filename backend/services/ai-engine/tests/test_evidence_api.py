from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from trialscribe_ai.api import evidence as routes
from trialscribe_ai.api.app import app
from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
)
from trialscribe_ai.models.evidence_chunk import EvidenceChunk
from trialscribe_ai.utils.constant import (
    INVALID_EVIDENCE_IDS_DETAIL,
    MAX_EVIDENCE_CHUNK_IDS,
)
from trialscribe_ai.utils.exceptions import (
    ConversationNotFoundError,
    InvalidEvidenceRequestError,
)

ACCOUNT_ID = UUID("51000000-0000-4000-8000-000000000021")
ORGANIZATION_ID = UUID("51000000-0000-4000-8000-000000000022")
CONVERSATION_ID = UUID("51000000-0000-4000-8000-000000000023")
FIRST_ID = UUID("51000000-0000-4000-8000-000000000031")
SECOND_ID = UUID("51000000-0000-4000-8000-000000000032")
FOREIGN_ID = UUID("51000000-0000-4000-8000-000000000099")


class FakeDatabaseRuntime:
    @asynccontextmanager
    async def transaction(self) -> Any:
        yield object()


class FakeEvidenceService:
    def __init__(self) -> None:
        self.chunks = [
            EvidenceChunk(
                id=FIRST_ID,
                organization_id=ORGANIZATION_ID,
                conversation_id=CONVERSATION_ID,
                source_kind="trial_data",
                source_identity="trial-1",
                page_number=None,
                start_char=0,
                end_char=18,
                text="FAROHEALTH_INCLUSION_AGE_18",
            ),
            EvidenceChunk(
                id=SECOND_ID,
                organization_id=ORGANIZATION_ID,
                conversation_id=CONVERSATION_ID,
                source_kind="web",
                source_identity="https://www.cdc.gov/x",
                page_number=2,
                start_char=0,
                end_char=8,
                text="CDC text",
            ),
        ]
        self.error: Exception | None = None
        self.requested_ids: list[UUID] | None = None

    async def get_many(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        ids: list[UUID],
    ) -> list[EvidenceChunk]:
        del organization_id, account_id, conversation_id
        if self.error is not None:
            raise self.error
        if not 1 <= len(ids) <= MAX_EVIDENCE_CHUNK_IDS:
            raise InvalidEvidenceRequestError
        self.requested_ids = list(ids)
        by_id = {chunk.id: chunk for chunk in self.chunks}
        return [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]


@pytest.fixture
def api_context(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, FakeEvidenceService]:
    service = FakeEvidenceService()
    monkeypatch.setattr(routes, "_service", lambda *_args: service)
    app.dependency_overrides[get_current_account_id] = lambda: ACCOUNT_ID
    app.dependency_overrides[get_current_organization_id] = lambda: ORGANIZATION_ID
    app.dependency_overrides[get_database_runtime] = lambda: FakeDatabaseRuntime()
    try:
        yield TestClient(app), service
    finally:
        app.dependency_overrides.clear()


def test_list_returns_requested_chunks_in_order(
    api_context: tuple[TestClient, FakeEvidenceService],
) -> None:
    client, service = api_context

    response = client.get(
        f"/conversations/{CONVERSATION_ID}/evidence-chunks",
        params=[("ids", str(SECOND_ID)), ("ids", str(FIRST_ID))],
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(SECOND_ID), str(FIRST_ID)]
    assert items[1]["text"] == "FAROHEALTH_INCLUSION_AGE_18"
    assert "embedding_model" not in items[0]
    assert service.requested_ids == [SECOND_ID, FIRST_ID]


def test_foreign_id_is_omitted(
    api_context: tuple[TestClient, FakeEvidenceService],
) -> None:
    client, _ = api_context

    response = client.get(
        f"/conversations/{CONVERSATION_ID}/evidence-chunks",
        params=[("ids", str(FIRST_ID)), ("ids", str(FOREIGN_ID))],
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(FIRST_ID)]


def test_missing_conversation_is_not_found(
    api_context: tuple[TestClient, FakeEvidenceService],
) -> None:
    client, service = api_context
    service.error = ConversationNotFoundError()

    response = client.get(
        f"/conversations/{CONVERSATION_ID}/evidence-chunks",
        params=[("ids", str(FIRST_ID))],
    )

    assert response.status_code == 404


def test_empty_ids_are_rejected(
    api_context: tuple[TestClient, FakeEvidenceService],
) -> None:
    client, _ = api_context

    response = client.get(f"/conversations/{CONVERSATION_ID}/evidence-chunks")

    assert response.status_code == 422
    assert response.json()["detail"] == INVALID_EVIDENCE_IDS_DETAIL


def test_too_many_ids_are_rejected(
    api_context: tuple[TestClient, FakeEvidenceService],
) -> None:
    client, _ = api_context
    extra = [UUID(int=index) for index in range(1, MAX_EVIDENCE_CHUNK_IDS + 2)]

    response = client.get(
        f"/conversations/{CONVERSATION_ID}/evidence-chunks",
        params=[("ids", str(chunk_id)) for chunk_id in extra],
    )

    assert response.status_code == 422
    assert response.json()["detail"] == INVALID_EVIDENCE_IDS_DETAIL
