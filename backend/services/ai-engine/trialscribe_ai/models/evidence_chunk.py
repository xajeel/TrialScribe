"""A stored passage the API may read for citation inspection.

This is not a SQLAlchemy mapped class. The worker already maps
`evidence_chunks` on the shared metadata; a second mapping collides when the
suite loads both services. Embedding columns stay unselected (B4).
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class EvidenceChunk:
    """One tenant-scoped passage, with provenance so a citation can resolve."""

    id: UUID
    organization_id: UUID
    conversation_id: UUID
    source_kind: str
    source_identity: str
    page_number: int | None
    start_char: int
    end_char: int
    text: str
