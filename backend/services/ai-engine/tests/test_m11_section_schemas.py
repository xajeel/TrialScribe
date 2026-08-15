from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trialscribe_ai.config.m11_catalog import (
    M11_CATALOG_VERSION,
    M11_SECTION_CATALOG,
)
from trialscribe_ai.schemas.m11_section import (
    M11RevisionPageQuery,
    M11SectionResponse,
    M11SectionReviseRequest,
    M11SectionTransitionRequest,
)
from trialscribe_ai.utils.enum import M11RevisionAction, M11SectionStatus

EXPECTED_TITLES = (
    "PROTOCOL SUMMARY",
    "INTRODUCTION",
    "TRIAL OBJECTIVES AND ASSOCIATED ESTIMANDS",
    "TRIAL DESIGN",
    "TRIAL POPULATION",
    "TRIAL INTERVENTION AND CONCOMITANT THERAPY",
    "PARTICIPANT DISCONTINUATION OF TRIAL INTERVENTION AND "
    "DISCONTINUATION OR WITHDRAWAL FROM TRIAL",
    "TRIAL ASSESSMENTS AND PROCEDURES",
    "ADVERSE EVENTS, SERIOUS ADVERSE EVENTS, PRODUCT COMPLAINTS, "
    "PREGNANCY AND POSTPARTUM INFORMATION, AND SPECIAL SAFETY SITUATIONS",
    "STATISTICAL CONSIDERATIONS",
    "TRIAL OVERSIGHT AND OTHER GENERAL CONSIDERATIONS",
    "APPENDIX: SUPPORTING DETAILS",
    "APPENDIX: GLOSSARY OF TERMS AND ABBREVIATIONS",
    "APPENDIX: REFERENCES",
)


def test_catalog_is_exact_versioned_and_ordered() -> None:
    assert M11_CATALOG_VERSION == "ICH_M11_STEP_4_2025_11_19"
    assert tuple(item.number for item in M11_SECTION_CATALOG) == tuple(
        str(number) for number in range(1, 15)
    )
    assert tuple(item.position for item in M11_SECTION_CATALOG) == tuple(range(1, 15))
    assert tuple(item.title for item in M11_SECTION_CATALOG) == EXPECTED_TITLES


def test_request_contracts_normalize_text_and_require_a_change() -> None:
    request = M11SectionReviseRequest(
        expected_revision=2,
        instructions="  Focus on endpoints  ",
        content="  Draft text  ",
    )

    assert request.instructions == "Focus on endpoints"
    assert request.content == "Draft text"
    assert M11SectionReviseRequest(expected_revision=0, content="").content == ""

    with pytest.raises(ValidationError):
        M11SectionReviseRequest(expected_revision=0)
    with pytest.raises(ValidationError):
        M11SectionReviseRequest(expected_revision=-1, content="draft")
    with pytest.raises(ValidationError):
        M11SectionTransitionRequest(expected_revision=-1)


def test_request_contracts_enforce_text_and_page_limits() -> None:
    with pytest.raises(ValidationError):
        M11SectionReviseRequest(expected_revision=0, instructions="x" * 20_001)
    with pytest.raises(ValidationError):
        M11SectionReviseRequest(expected_revision=0, content="x" * 200_001)
    with pytest.raises(ValidationError):
        M11RevisionPageQuery(limit=101)
    with pytest.raises(ValidationError):
        M11RevisionPageQuery(after_revision=-1)

    assert M11RevisionPageQuery().limit == 20


def test_response_contract_accepts_orm_shaped_values_and_enums_serialize() -> None:
    now = datetime(2026, 7, 28, tzinfo=UTC)
    section_id = uuid4()
    conversation_id = uuid4()
    organization_id = uuid4()
    response = M11SectionResponse.model_validate(
        {
            "id": section_id,
            "conversation_id": conversation_id,
            "organization_id": organization_id,
            "catalog_version": M11_CATALOG_VERSION,
            "section_number": "1",
            "title": EXPECTED_TITLES[0],
            "position": 1,
            "instructions": "",
            "content": "",
            "status": "draft",
            "current_revision": 0,
            "completed_at": None,
            "completed_by_account_id": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert response.status is M11SectionStatus.DRAFT
    assert M11RevisionAction.REOPENED.value == "reopened"
    assert M11RevisionAction.GENERATED.value == "generated"
    assert M11RevisionAction.RESTORED.value == "restored"
    assert response.model_dump(mode="json")["status"] == "draft"
