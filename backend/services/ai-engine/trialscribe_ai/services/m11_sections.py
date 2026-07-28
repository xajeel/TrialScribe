"""ICH M11 section authorization, editing, and revision use cases."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from trialscribe_ai.config.m11_catalog import (
    M11_SECTION_CATALOG,
    M11SectionDefinition,
)
from trialscribe_ai.models.conversation import Conversation
from trialscribe_ai.models.m11_section import M11Section
from trialscribe_ai.models.m11_section_revision import M11SectionRevision
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.repositories.m11_section_revisions import (
    M11SectionRevisionRepository,
)
from trialscribe_ai.repositories.m11_sections import M11SectionRepository
from trialscribe_ai.utils.constant import (
    M11_CONTENT_MAX_LENGTH,
    M11_INSTRUCTIONS_MAX_LENGTH,
    MAX_PAGE_LIMIT,
)
from trialscribe_ai.utils.enum import M11RevisionAction, M11SectionStatus
from trialscribe_ai.utils.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    InvalidM11SectionInputError,
    M11SectionNotFoundError,
    M11SectionRevisionConflictError,
    M11SectionTransitionError,
)


class M11SectionService:
    """Manage a conversation's M11 workspace through injected repositories."""

    def __init__(
        self,
        conversations: ConversationRepository,
        sections: M11SectionRepository,
        revisions: M11SectionRevisionRepository,
    ) -> None:
        self._conversations = conversations
        self._sections = sections
        self._revisions = revisions

    @staticmethod
    def catalog() -> Sequence[M11SectionDefinition]:
        return M11_SECTION_CATALOG

    async def initialize_workspace(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
    ) -> list[M11Section]:
        conversation = await self._require_conversation(
            organization_id,
            account_id,
            conversation_id,
            for_update=True,
        )
        self._require_mutable(conversation)
        existing = await self._sections.list_for_conversation(
            conversation_id,
            organization_id,
        )
        if existing:
            if len(existing) != len(M11_SECTION_CATALOG):
                raise M11SectionTransitionError
            return existing
        return await self._sections.add_catalog(
            conversation_id,
            organization_id,
            M11_SECTION_CATALOG,
        )

    async def list_sections(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
    ) -> list[M11Section]:
        await self._require_conversation(
            organization_id,
            account_id,
            conversation_id,
        )
        return await self._sections.list_for_conversation(
            conversation_id,
            organization_id,
        )

    async def get_section(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        section_number: str,
    ) -> M11Section:
        await self._require_conversation(
            organization_id,
            account_id,
            conversation_id,
        )
        return await self._require_section(
            organization_id,
            conversation_id,
            section_number,
        )

    async def revise_section(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        expected_revision: int,
        instructions: str | None,
        content: str | None,
        now: datetime,
    ) -> M11Section:
        normalized_instructions, normalized_content = self._validate_revision_input(
            expected_revision,
            instructions,
            content,
        )
        section = await self._locked_mutable_section(
            organization_id,
            account_id,
            conversation_id,
            section_number,
        )
        self._require_revision(section, expected_revision)
        if section.status != M11SectionStatus.DRAFT:
            raise M11SectionTransitionError
        if normalized_instructions is not None:
            section.instructions = normalized_instructions
        if normalized_content is not None:
            section.content = normalized_content
        await self._record_action(
            section,
            account_id,
            M11RevisionAction.REVISED,
            now,
        )
        return section

    async def mark_done(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        expected_revision: int,
        now: datetime,
    ) -> M11Section:
        self._validate_expected_revision(expected_revision)
        section = await self._locked_mutable_section(
            organization_id,
            account_id,
            conversation_id,
            section_number,
        )
        self._require_revision(section, expected_revision)
        if section.status != M11SectionStatus.DRAFT or not section.content.strip():
            raise M11SectionTransitionError
        section.status = M11SectionStatus.DONE.value
        section.completed_at = now
        section.completed_by_account_id = account_id
        await self._record_action(section, account_id, M11RevisionAction.DONE, now)
        return section

    async def reopen(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        expected_revision: int,
        now: datetime,
    ) -> M11Section:
        self._validate_expected_revision(expected_revision)
        section = await self._locked_mutable_section(
            organization_id,
            account_id,
            conversation_id,
            section_number,
        )
        self._require_revision(section, expected_revision)
        if section.status != M11SectionStatus.DONE:
            raise M11SectionTransitionError
        section.status = M11SectionStatus.DRAFT.value
        section.completed_at = None
        section.completed_by_account_id = None
        await self._record_action(
            section,
            account_id,
            M11RevisionAction.REOPENED,
            now,
        )
        return section

    async def list_revisions(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        after_revision: int,
        limit: int,
    ) -> tuple[list[M11SectionRevision], int | None]:
        if after_revision < 0 or not 1 <= limit <= MAX_PAGE_LIMIT:
            raise InvalidM11SectionInputError
        section = await self.get_section(
            organization_id,
            account_id,
            conversation_id,
            section_number,
        )
        return await self._revisions.list_for_section(
            section.id,
            conversation_id,
            organization_id,
            after_revision=after_revision,
            limit=limit,
        )

    async def _locked_mutable_section(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        section_number: str,
    ) -> M11Section:
        conversation = await self._require_conversation(
            organization_id,
            account_id,
            conversation_id,
            for_update=True,
        )
        self._require_mutable(conversation)
        return await self._require_section(
            organization_id,
            conversation_id,
            section_number,
            for_update=True,
        )

    async def _record_action(
        self,
        section: M11Section,
        account_id: UUID,
        action: M11RevisionAction,
        now: datetime,
    ) -> None:
        section.current_revision += 1
        await self._sections.flush(section)
        await self._revisions.append(section, account_id, action, now)

    async def _require_conversation(
        self,
        organization_id: UUID,
        account_id: UUID,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation:
        conversation = await self._conversations.get_accessible(
            organization_id,
            account_id,
            conversation_id,
            for_update=for_update,
        )
        if conversation is None:
            raise ConversationNotFoundError
        return conversation

    async def _require_section(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        for_update: bool = False,
    ) -> M11Section:
        section = await self._sections.get_by_number(
            conversation_id,
            organization_id,
            section_number,
            for_update=for_update,
        )
        if section is None:
            raise M11SectionNotFoundError
        return section

    @staticmethod
    def _require_mutable(conversation: Conversation) -> None:
        if conversation.archived_at is not None:
            raise ConversationArchivedError

    @staticmethod
    def _validate_expected_revision(expected_revision: int) -> None:
        if expected_revision < 0:
            raise InvalidM11SectionInputError

    @classmethod
    def _validate_revision_input(
        cls,
        expected_revision: int,
        instructions: str | None,
        content: str | None,
    ) -> tuple[str | None, str | None]:
        cls._validate_expected_revision(expected_revision)
        if instructions is None and content is None:
            raise InvalidM11SectionInputError
        normalized_instructions = instructions.strip() if instructions is not None else None
        normalized_content = content.strip() if content is not None else None
        if (
            normalized_instructions is not None
            and len(normalized_instructions) > M11_INSTRUCTIONS_MAX_LENGTH
        ):
            raise InvalidM11SectionInputError
        if (
            normalized_content is not None
            and len(normalized_content) > M11_CONTENT_MAX_LENGTH
        ):
            raise InvalidM11SectionInputError
        return normalized_instructions, normalized_content

    @staticmethod
    def _require_revision(section: M11Section, expected_revision: int) -> None:
        if section.current_revision != expected_revision:
            raise M11SectionRevisionConflictError
