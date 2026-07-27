from datetime import UTC, datetime
from uuid import uuid4

from trialscribe_ai.models.document import Document
from trialscribe_ai.schemas.document import DocumentResponse


def constraint_names(model: type[object]) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints  # type: ignore[attr-defined]
        if constraint.name is not None
    }


def test_document_keeps_tenant_and_validation_constraints() -> None:
    names = constraint_names(Document)
    assert "ck_documents_kind" in names
    assert "ck_documents_status" in names
    assert "ck_documents_byte_size_positive" in names
    assert "ck_documents_filename_length" in names
    assert "fk_documents_conversation_organization" in names


def test_document_response_accepts_orm_values() -> None:
    now = datetime(2026, 7, 24, tzinfo=UTC)
    document = Document(
        id=uuid4(),
        conversation_id=uuid4(),
        organization_id=uuid4(),
        uploaded_by_account_id=uuid4(),
        kind="trial_data",
        filename="trial.json",
        content_type="application/json",
        byte_size=42,
        status="pending",
        error=None,
        content=b"{}",
        created_at=now,
        updated_at=now,
    )

    response = DocumentResponse.model_validate(document)

    assert response.kind.value == "trial_data"
    assert response.status.value == "pending"
    assert response.byte_size == 42
    assert response.error is None
