"""A conversation M11 section the worker may update without owning the table."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class M11SectionRecord:
    """The live authoring state of one tenant-scoped M11 section."""

    id: UUID
    organization_id: UUID
    conversation_id: UUID
    section_number: str
    title: str
    instructions: str
    content: str
    status: str
    current_revision: int
