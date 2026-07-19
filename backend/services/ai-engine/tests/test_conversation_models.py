from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.conversation_access import ConversationAccess
from trialscribe_ai.models.conversation_message import ConversationMessage
from trialscribe_ai.schemas.conversation import (
    ConversationCollaboratorsReplaceRequest,
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessageResponse,
    ConversationPageQuery,
)


def constraint_names(model: type[object]) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints  # type: ignore[attr-defined]
        if constraint.name is not None
    }


def test_models_keep_tenant_and_ordering_constraints() -> None:
    assert "uq_conversations_id_organization_id" in constraint_names(Conversation)
    assert (
        "uq_conversation_access_conversation_id_account_id"
        in constraint_names(ConversationAccess)
    )
    assert (
        "fk_conversation_access_organization_membership"
        in constraint_names(ConversationAccess)
    )
    assert (
        "uq_conversation_messages_conversation_id_sequence"
        in constraint_names(ConversationMessage)
    )
    assert "ck_conversation_messages_role" in constraint_names(ConversationMessage)


def test_request_contracts_trim_text_and_reject_unsafe_boundaries() -> None:
    assert ConversationCreateRequest(title="  Protocol  ").title == "Protocol"
    assert ConversationMessageCreateRequest(content="  Continue  ").content == "Continue"

    for title in ("", "   ", "x" * 121):
        with pytest.raises(ValidationError):
            ConversationCreateRequest(title=title)
    for content in ("", "   ", "x" * 20_001):
        with pytest.raises(ValidationError):
            ConversationMessageCreateRequest(content=content)


def test_collaborators_and_page_limits_are_bounded() -> None:
    account_id = uuid4()
    with pytest.raises(ValidationError):
        ConversationCollaboratorsReplaceRequest(account_ids=[account_id, account_id])
    with pytest.raises(ValidationError):
        ConversationCollaboratorsReplaceRequest(
            account_ids=[uuid4() for _ in range(101)]
        )
    assert ConversationPageQuery().limit == 20
    with pytest.raises(ValidationError):
        ConversationPageQuery(limit=101)


def test_message_response_accepts_orm_values() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    message = ConversationMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        organization_id=uuid4(),
        author_account_id=None,
        role="assistant",
        content="Draft ready",
        sequence=1,
        created_at=now,
        updated_at=now,
    )

    response = ConversationMessageResponse.model_validate(message)

    assert response.role.value == "assistant"
    assert response.sequence == 1
