"""Read and revise M11 sections with both tenant columns on every statement."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_worker.models.m11_section_record import M11SectionRecord
from trialscribe_worker.utils.constant import (
    GENERATE_CONTENT_MAX_LENGTH,
    M11_REVISION_ACTION_REVISED,
    M11_SECTION_DRAFT_STATUS,
)

_GET_SCOPED = text(
    "SELECT id, organization_id, conversation_id, section_number, title, "
    "instructions, content, status, current_revision "
    "FROM trialscribe.m11_sections "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "AND section_number = :section_number"
)
_REVISE_DRAFT = text(
    "UPDATE trialscribe.m11_sections "
    "SET content = :content, current_revision = current_revision + 1, "
    "updated_at = :now "
    "WHERE organization_id = :organization_id "
    "AND conversation_id = :conversation_id "
    "AND section_number = :section_number "
    "AND status = :draft_status "
    "AND current_revision = :expected_revision "
    "RETURNING id, instructions, content, current_revision"
)
_TOUCH_CONVERSATION = text(
    "UPDATE trialscribe.conversations SET last_activity_at = :now, "
    "updated_at = :now "
    "WHERE id = :conversation_id AND organization_id = :organization_id"
)
_INSERT_REVISION = text(
    "INSERT INTO trialscribe.m11_section_revisions ("
    "id, created_at, updated_at, section_id, conversation_id, organization_id, "
    "revision_number, action, instructions, content, status, author_account_id"
    ") VALUES ("
    ":id, :now, :now, :section_id, :conversation_id, :organization_id, "
    ":revision_number, :action, :instructions, :content, :status, "
    ":author_account_id"
    ")"
)


class M11SectionStore:
    """Load one section, or write a draft revision, inside this tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
    ) -> M11SectionRecord | None:
        """Load one M11 section that belongs to this organization and conversation."""

        result = await self._session.execute(
            _GET_SCOPED,
            {
                "organization_id": organization_id,
                "conversation_id": conversation_id,
                "section_number": section_number,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return M11SectionRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            conversation_id=row["conversation_id"],
            section_number=row["section_number"],
            title=row["title"],
            instructions=row["instructions"],
            content=row["content"],
            status=row["status"],
            current_revision=row["current_revision"],
        )

    async def revise_draft(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        expected_revision: int,
        content: str,
        author_account_id: UUID,
        now: datetime,
        action: str = M11_REVISION_ACTION_REVISED,
    ) -> bool:
        """Save a draft revision when the expected number still matches."""

        if not 1 <= len(content) <= GENERATE_CONTENT_MAX_LENGTH:
            return False
        result = await self._session.execute(
            _REVISE_DRAFT,
            {
                "content": content,
                "now": now,
                "organization_id": organization_id,
                "conversation_id": conversation_id,
                "section_number": section_number,
                "draft_status": M11_SECTION_DRAFT_STATUS,
                "expected_revision": expected_revision,
            },
        )
        row = result.mappings().first()
        if row is None:
            return False
        await self._session.execute(
            _TOUCH_CONVERSATION,
            {
                "now": now,
                "conversation_id": conversation_id,
                "organization_id": organization_id,
            },
        )
        await self._session.execute(
            _INSERT_REVISION,
            {
                "id": uuid4(),
                "now": now,
                "section_id": row["id"],
                "conversation_id": conversation_id,
                "organization_id": organization_id,
                "revision_number": row["current_revision"],
                "action": action,
                "instructions": row["instructions"],
                "content": row["content"],
                "status": M11_SECTION_DRAFT_STATUS,
                "author_account_id": author_account_id,
            },
        )
        return True
