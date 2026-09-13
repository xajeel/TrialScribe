"""Public contracts for inspecting stored evidence passages."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvidenceChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    organization_id: UUID
    source_kind: str
    source_identity: str
    page_number: int | None
    start_char: int
    end_char: int
    text: str


class EvidenceChunkListResponse(BaseModel):
    items: list[EvidenceChunkResponse]
