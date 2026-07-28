import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_ai.config.m11_catalog import M11_SECTION_CATALOG
from trialscribe_ai.models.m11_section import M11Section
from trialscribe_ai.models.m11_section_revision import M11SectionRevision
from trialscribe_ai.repositories.m11_section_revisions import (
    M11SectionRevisionRepository,
)
from trialscribe_ai.repositories.m11_sections import M11SectionRepository
from trialscribe_ai.utils.enum import M11RevisionAction

ORGANIZATION_ID = UUID("70000000-0000-4000-8000-000000000001")
CONVERSATION_ID = UUID("70000000-0000-4000-8000-000000000002")
ACCOUNT_ID = UUID("70000000-0000-4000-8000-000000000003")
NOW = datetime(2026, 7, 28, tzinfo=UTC)


def section(revision: int = 1) -> M11Section:
    return M11Section(
        id=uuid4(),
        conversation_id=CONVERSATION_ID,
        organization_id=ORGANIZATION_ID,
        catalog_version="ICH_M11_STEP_4_2025_11_19",
        section_number="1",
        title="PROTOCOL SUMMARY",
        position=1,
        instructions="Use plain language.",
        content="Draft summary.",
        status="draft",
        current_revision=revision,
    )


def test_catalog_insert_copies_every_official_definition_in_order() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = M11SectionRepository(session)

    result = asyncio.run(
        repository.add_catalog(
            CONVERSATION_ID,
            ORGANIZATION_ID,
            M11_SECTION_CATALOG,
        )
    )

    assert len(result) == 14
    assert [item.section_number for item in result] == [
        str(number) for number in range(1, 15)
    ]
    assert [item.position for item in result] == list(range(1, 15))
    assert all(item.conversation_id == CONVERSATION_ID for item in result)
    assert all(item.organization_id == ORGANIZATION_ID for item in result)
    assert all(item.current_revision == 0 for item in result)
    session.add_all.assert_called_once_with(result)
    session.flush.assert_awaited_once()


def test_section_queries_always_scope_conversation_and_tenant_and_order() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = []
    repository = M11SectionRepository(session)

    asyncio.run(repository.list_for_conversation(CONVERSATION_ID, ORGANIZATION_ID))

    statement = session.scalars.await_args.args[0]
    compiled = str(statement)
    assert "m11_sections.conversation_id" in compiled
    assert "m11_sections.organization_id" in compiled
    assert "ORDER BY trialscribe.m11_sections.position" in compiled


def test_exact_section_lookup_can_lock_and_stays_tenant_scoped() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    repository = M11SectionRepository(session)

    asyncio.run(
        repository.get_by_number(
            CONVERSATION_ID,
            ORGANIZATION_ID,
            "1",
            for_update=True,
        )
    )

    statement = str(session.scalar.await_args.args[0])
    assert "m11_sections.conversation_id" in statement
    assert "m11_sections.organization_id" in statement
    assert "m11_sections.section_number" in statement
    assert "FOR UPDATE" in statement


def test_revision_append_copies_the_complete_post_action_snapshot() -> None:
    current = section(revision=3)
    current.status = "done"
    session = AsyncMock(spec=AsyncSession)
    repository = M11SectionRevisionRepository(session)

    revision = asyncio.run(
        repository.append(current, ACCOUNT_ID, M11RevisionAction.DONE, NOW)
    )

    assert revision.section_id == current.id
    assert revision.conversation_id == CONVERSATION_ID
    assert revision.organization_id == ORGANIZATION_ID
    assert revision.revision_number == 3
    assert revision.action == "done"
    assert revision.instructions == current.instructions
    assert revision.content == current.content
    assert revision.status == "done"
    assert revision.author_account_id == ACCOUNT_ID
    assert revision.created_at == NOW
    session.add.assert_called_once_with(revision)
    session.flush.assert_awaited_once()


def test_revision_page_is_scoped_ascending_and_uses_limit_plus_one() -> None:
    current = section()
    revisions = [
        M11SectionRevision(
            id=uuid4(),
            section_id=current.id,
            conversation_id=CONVERSATION_ID,
            organization_id=ORGANIZATION_ID,
            revision_number=number,
            action="revised",
            instructions="",
            content=f"Revision {number}",
            status="draft",
            author_account_id=ACCOUNT_ID,
        )
        for number in range(2, 5)
    ]
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = revisions
    repository = M11SectionRevisionRepository(session)

    items, cursor = asyncio.run(
        repository.list_for_section(
            current.id,
            CONVERSATION_ID,
            ORGANIZATION_ID,
            after_revision=1,
            limit=2,
        )
    )

    statement = session.scalars.await_args.args[0]
    compiled = str(statement)
    assert items == revisions[:2]
    assert cursor == 3
    assert statement._limit_clause.value == 3
    assert "m11_section_revisions.section_id" in compiled
    assert "m11_section_revisions.conversation_id" in compiled
    assert "m11_section_revisions.organization_id" in compiled
    assert (
        "ORDER BY trialscribe.m11_section_revisions.revision_number" in compiled
    )
