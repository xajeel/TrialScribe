import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.m11_section import M11Section
from trialscribe_ai.models.m11_section_revision import M11SectionRevision
from trialscribe_ai.services.m11_sections import M11SectionService
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    InvalidM11SectionInputError,
    M11SectionNotFoundError,
    M11SectionRevisionConflictError,
    M11SectionTransitionError,
)

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("71000000-0000-4000-8000-000000000001")
OTHER_ORGANIZATION_ID = UUID("71000000-0000-4000-8000-000000000002")
OWNER_ID = UUID("71000000-0000-4000-8000-000000000003")
COLLABORATOR_ID = UUID("71000000-0000-4000-8000-000000000004")
STRANGER_ID = UUID("71000000-0000-4000-8000-000000000005")


class FakeConversationRepository:
    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation
        self.grants = {OWNER_ID, COLLABORATOR_ID}
        self.last_locked = False
        self.flush_calls = 0

    async def get_accessible(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        self.last_locked = for_update
        if (
            conversation_id != self.conversation.id
            or organization_id != self.conversation.organization_id
            or account_id not in self.grants
        ):
            return None
        return self.conversation

    async def flush(self, conversation: Conversation) -> Conversation:
        self.flush_calls += 1
        return conversation


class FakeSectionRepository:
    def __init__(self) -> None:
        self.items: dict[str, M11Section] = {}
        self.add_calls = 0
        self.last_locked = False

    async def add_catalog(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        definitions: object,
    ) -> list[M11Section]:
        self.add_calls += 1
        for definition in definitions:  # type: ignore[union-attr]
            item = M11Section(
                id=uuid4(),
                conversation_id=conversation_id,
                organization_id=organization_id,
                catalog_version="ICH_M11_STEP_4_2025_11_19",
                section_number=definition.number,
                title=definition.title,
                position=definition.position,
                instructions="",
                content="",
                status="draft",
                current_revision=0,
                completed_at=None,
                completed_by_account_id=None,
                created_at=NOW,
                updated_at=NOW,
            )
            self.items[item.section_number] = item
        return await self.list_for_conversation(conversation_id, organization_id)

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        organization_id: UUID,
    ) -> list[M11Section]:
        return sorted(
            (
                item
                for item in self.items.values()
                if item.conversation_id == conversation_id
                and item.organization_id == organization_id
            ),
            key=lambda item: item.position,
        )

    async def get_by_number(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        section_number: str,
        *,
        for_update: bool = False,
    ) -> M11Section | None:
        self.last_locked = for_update
        item = self.items.get(section_number)
        if (
            item is None
            or item.conversation_id != conversation_id
            or item.organization_id != organization_id
        ):
            return None
        return item

    async def flush(self, section: M11Section) -> M11Section:
        section.updated_at = NOW
        return section


class FakeRevisionRepository:
    def __init__(self) -> None:
        self.items: list[M11SectionRevision] = []

    async def append(
        self,
        section: M11Section,
        author_account_id: UUID,
        action: object,
        created_at: datetime,
    ) -> M11SectionRevision:
        revision = M11SectionRevision(
            id=uuid4(),
            section_id=section.id,
            conversation_id=section.conversation_id,
            organization_id=section.organization_id,
            revision_number=section.current_revision,
            action=action.value,  # type: ignore[union-attr]
            instructions=section.instructions,
            content=section.content,
            status=section.status,
            author_account_id=author_account_id,
            created_at=created_at,
            updated_at=created_at,
        )
        self.items.append(revision)
        return revision

    async def list_for_section(
        self,
        section_id: UUID,
        conversation_id: UUID,
        organization_id: UUID,
        *,
        after_revision: int,
        limit: int,
    ) -> tuple[list[M11SectionRevision], int | None]:
        items = [
            item
            for item in self.items
            if item.section_id == section_id
            and item.conversation_id == conversation_id
            and item.organization_id == organization_id
            and item.revision_number > after_revision
        ]
        page = items[:limit]
        next_after = page[-1].revision_number if len(items) > limit else None
        return page, next_after

    async def get_scoped(
        self,
        section_id: UUID,
        conversation_id: UUID,
        organization_id: UUID,
        revision_number: int,
    ) -> M11SectionRevision | None:
        for item in self.items:
            if (
                item.section_id == section_id
                and item.conversation_id == conversation_id
                and item.organization_id == organization_id
                and item.revision_number == revision_number
            ):
                return item
        return None


def service_context() -> tuple[
    M11SectionService,
    Conversation,
    FakeConversationRepository,
    FakeSectionRepository,
    FakeRevisionRepository,
]:
    conversation = Conversation(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        owner_account_id=OWNER_ID,
        title="Protocol",
        last_activity_at=NOW,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    conversations = FakeConversationRepository(conversation)
    sections = FakeSectionRepository()
    revisions = FakeRevisionRepository()
    return (
        M11SectionService(  # type: ignore[arg-type]
            conversations,
            sections,
            revisions,
        ),
        conversation,
        conversations,
        sections,
        revisions,
    )


def initialize(
    service: M11SectionService,
    account_id: UUID = OWNER_ID,
) -> list[M11Section]:
    return asyncio.run(
        service.initialize_workspace(
            ORGANIZATION_ID,
            account_id,
            service._conversations.conversation.id,  # type: ignore[attr-defined]
        )
    )


def test_catalog_and_initialization_are_exact_ordered_and_idempotent() -> None:
    service, conversation, conversations, sections, _ = service_context()

    first = initialize(service)
    second = initialize(service)

    assert len(service.catalog()) == 14
    assert [item.section_number for item in first] == [
        str(number) for number in range(1, 15)
    ]
    assert first == second
    assert sections.add_calls == 1
    assert conversations.last_locked is True
    assert all(item.conversation_id == conversation.id for item in first)


def test_collaborator_can_revise_and_history_keeps_complete_snapshot() -> None:
    service, conversation, conversations, sections, revisions = service_context()
    initialize(service)

    revised = asyncio.run(
        service.revise_section(
            ORGANIZATION_ID,
            COLLABORATOR_ID,
            conversation.id,
            "1",
            expected_revision=0,
            instructions="  Use plain language.  ",
            content="  Draft summary.  ",
            now=NOW,
        )
    )
    history, cursor = asyncio.run(
        service.list_revisions(
            ORGANIZATION_ID,
            COLLABORATOR_ID,
            conversation.id,
            "1",
            after_revision=0,
            limit=20,
        )
    )

    assert revised.instructions == "Use plain language."
    assert revised.content == "Draft summary."
    assert revised.current_revision == 1
    assert conversations.last_locked is False
    assert sections.last_locked is False
    assert len(history) == 1
    assert history[0].action == "revised"
    assert history[0].content == revised.content
    assert history[0].author_account_id == COLLABORATOR_ID
    assert cursor is None
    assert len(revisions.items) == 1


def test_done_reopen_and_revision_actions_form_a_guarded_state_machine() -> None:
    service, conversation, _, _, revisions = service_context()
    initialize(service)
    section = asyncio.run(
        service.revise_section(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=0,
            instructions=None,
            content="Final candidate",
            now=NOW,
        )
    )

    done = asyncio.run(
        service.mark_done(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=section.current_revision,
            now=NOW,
        )
    )
    assert done.status == "done"
    assert done.current_revision == 2
    assert done.completed_at == NOW
    assert done.completed_by_account_id == OWNER_ID

    reopened = asyncio.run(
        service.reopen(
            ORGANIZATION_ID,
            COLLABORATOR_ID,
            conversation.id,
            "1",
            expected_revision=done.current_revision,
            now=NOW,
        )
    )
    assert reopened.status == "draft"
    assert reopened.current_revision == 3
    assert reopened.completed_at is None
    assert reopened.completed_by_account_id is None
    assert [item.action for item in revisions.items] == [
        "revised",
        "done",
        "reopened",
    ]


def test_section_mutations_advance_conversation_activity() -> None:
    service, conversation, conversations, _, _ = service_context()
    initialize(service)

    revised_at = NOW + timedelta(minutes=1)
    section = asyncio.run(
        service.revise_section(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=0,
            instructions=None,
            content="Ready",
            now=revised_at,
        )
    )
    assert conversation.last_activity_at == revised_at

    done_at = NOW + timedelta(minutes=2)
    section = asyncio.run(
        service.mark_done(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=section.current_revision,
            now=done_at,
        )
    )
    assert conversation.last_activity_at == done_at

    reopened_at = NOW + timedelta(minutes=3)
    asyncio.run(
        service.reopen(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=section.current_revision,
            now=reopened_at,
        )
    )
    assert conversation.last_activity_at == reopened_at
    assert conversations.flush_calls == 3


def test_access_archive_missing_and_partial_workspace_rules_are_enforced() -> None:
    service, conversation, _, sections, _ = service_context()

    with pytest.raises(ConversationNotFoundError):
        asyncio.run(
            service.list_sections(
                OTHER_ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
            )
        )
    with pytest.raises(ConversationNotFoundError):
        asyncio.run(
            service.list_sections(
                ORGANIZATION_ID,
                STRANGER_ID,
                conversation.id,
            )
        )

    initialize(service)
    with pytest.raises(M11SectionNotFoundError):
        asyncio.run(
            service.get_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "99",
            )
        )

    sections.items.pop("14")
    with pytest.raises(M11SectionTransitionError):
        initialize(service)

    conversation.archived_at = NOW
    with pytest.raises(ConversationArchivedError):
        asyncio.run(
            service.revise_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=0,
                instructions=None,
                content="Blocked",
                now=NOW,
            )
        )
    assert len(
        asyncio.run(
            service.list_sections(ORGANIZATION_ID, OWNER_ID, conversation.id)
        )
    ) == 13


def test_invalid_stale_and_illegal_transition_inputs_are_rejected() -> None:
    service, conversation, _, _, _ = service_context()
    sections = initialize(service)

    with pytest.raises(InvalidM11SectionInputError):
        asyncio.run(
            service.revise_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=0,
                instructions=None,
                content=None,
                now=NOW,
            )
        )
    with pytest.raises(InvalidM11SectionInputError):
        asyncio.run(
            service.list_revisions(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                after_revision=-1,
                limit=20,
            )
        )
    with pytest.raises(M11SectionRevisionConflictError):
        asyncio.run(
            service.revise_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=4,
                instructions=None,
                content="Stale",
                now=NOW,
            )
        )
    with pytest.raises(M11SectionTransitionError):
        asyncio.run(
            service.mark_done(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=0,
                now=NOW,
            )
        )
    with pytest.raises(M11SectionTransitionError):
        asyncio.run(
            service.reopen(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "2",
                expected_revision=0,
                now=NOW,
            )
        )

    sections[0].content = "Ready"
    done = asyncio.run(
        service.mark_done(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=0,
            now=NOW,
        )
    )
    with pytest.raises(M11SectionTransitionError):
        asyncio.run(
            service.revise_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=done.current_revision,
                instructions=None,
                content="Must reopen first",
                now=NOW,
            )
        )


def test_restore_copies_an_earlier_snapshot_onto_the_draft() -> None:
    service, conversation, conversations, _, revisions = service_context()
    initialize(service)
    first = asyncio.run(
        service.revise_section(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=0,
            instructions="First note",
            content="First wording",
            now=NOW,
        )
    )
    asyncio.run(
        service.revise_section(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=first.current_revision,
            instructions="Later note",
            content="Later wording",
            now=NOW,
        )
    )
    restored = asyncio.run(
        service.restore_section(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=2,
            revision_number=1,
            now=NOW,
        )
    )
    assert restored.content == "First wording"
    assert restored.instructions == "First note"
    assert restored.current_revision == 3
    assert revisions.items[-1].action == "restored"
    assert conversations.flush_calls >= 1


def test_restore_rejects_done_stale_and_missing_snapshots() -> None:
    service, conversation, _, _, _ = service_context()
    initialize(service)
    asyncio.run(
        service.revise_section(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=0,
            instructions=None,
            content="Ready",
            now=NOW,
        )
    )
    done = asyncio.run(
        service.mark_done(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=1,
            now=NOW,
        )
    )
    with pytest.raises(M11SectionTransitionError):
        asyncio.run(
            service.restore_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=done.current_revision,
                revision_number=1,
                now=NOW,
            )
        )
    asyncio.run(
        service.reopen(
            ORGANIZATION_ID,
            OWNER_ID,
            conversation.id,
            "1",
            expected_revision=done.current_revision,
            now=NOW,
        )
    )
    with pytest.raises(M11SectionRevisionConflictError):
        asyncio.run(
            service.restore_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=0,
                revision_number=1,
                now=NOW,
            )
        )
    with pytest.raises(M11SectionNotFoundError):
        asyncio.run(
            service.restore_section(
                ORGANIZATION_ID,
                OWNER_ID,
                conversation.id,
                "1",
                expected_revision=3,
                revision_number=99,
                now=NOW,
            )
        )
