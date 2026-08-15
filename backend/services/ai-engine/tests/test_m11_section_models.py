from datetime import UTC, datetime
from uuid import uuid4

from trialscribe_ai.models import M11Section, M11SectionRevision
from trialscribe_ai.schemas.m11_section import (
    M11SectionResponse,
    M11SectionRevisionResponse,
)
from trialscribe_ai.utils.enum import M11RevisionAction


def constraint_names(model: type[object]) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints  # type: ignore[attr-defined]
        if constraint.name is not None
    }


def test_section_model_keeps_tenant_order_state_and_text_constraints() -> None:
    names = constraint_names(M11Section)

    assert "fk_m11_sections_conversation_organization" in names
    assert "uq_m11_sections_id_conversation_organization" in names
    assert "uq_m11_sections_conversation_number" in names
    assert "uq_m11_sections_conversation_position" in names
    assert "ck_m11_sections_status" in names
    assert "ck_m11_sections_completion_state" in names
    assert "ck_m11_sections_instructions_length" in names
    assert "ck_m11_sections_content_length" in names


def test_revision_model_is_scoped_ordered_and_action_checked() -> None:
    names = constraint_names(M11SectionRevision)

    assert "fk_m11_section_revisions_section_conversation_organization" in names
    assert "uq_m11_section_revisions_section_revision" in names
    assert "ck_m11_section_revisions_number_positive" in names
    assert "ck_m11_section_revisions_action" in names
    assert "ck_m11_section_revisions_action_status" in names


def test_section_and_revision_responses_accept_orm_values() -> None:
    now = datetime(2026, 7, 28, tzinfo=UTC)
    section = M11Section(
        id=uuid4(),
        conversation_id=uuid4(),
        organization_id=uuid4(),
        catalog_version="ICH_M11_STEP_4_2025_11_19",
        section_number="1",
        title="PROTOCOL SUMMARY",
        position=1,
        instructions="Summarise.",
        content="Draft",
        status="draft",
        current_revision=1,
        completed_at=None,
        completed_by_account_id=None,
        created_at=now,
        updated_at=now,
    )
    revision = M11SectionRevision(
        id=uuid4(),
        section_id=section.id,
        conversation_id=section.conversation_id,
        organization_id=section.organization_id,
        revision_number=1,
        action="revised",
        instructions=section.instructions,
        content=section.content,
        status=section.status,
        author_account_id=uuid4(),
        created_at=now,
        updated_at=now,
    )

    assert M11SectionResponse.model_validate(section).status.value == "draft"
    assert M11SectionRevisionResponse.model_validate(revision).action.value == "revised"
    assert M11RevisionAction.GENERATED.value == "generated"
    assert M11RevisionAction.RESTORED.value == "restored"
