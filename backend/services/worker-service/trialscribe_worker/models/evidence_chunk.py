"""A passage whose text lives in PostgreSQL and whose vector lives in Chroma."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_worker.utils.constant import (
    EVIDENCE_CHAR_SPAN_CHECK,
    EVIDENCE_DIMENSIONS_CHECK,
    EVIDENCE_ORGANIZATION_CONVERSATION_INDEX,
    EVIDENCE_SOURCE_KIND_CHECK,
    EVIDENCE_TEXT_LENGTH_CHECK,
    MAX_MODEL_NAME_LENGTH,
    MAX_SOURCE_IDENTITY_LENGTH,
    MAX_SOURCE_KIND_LENGTH,
)


class EvidenceChunk(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One tenant-scoped passage, with provenance so a citation can resolve.

    The composite foreign key to conversations lives in migration
    `0013_evidence_chunks`. That table belongs to another service's package.
    """

    __tablename__ = "evidence_chunks"
    __table_args__ = (
        CheckConstraint(EVIDENCE_SOURCE_KIND_CHECK, name="ck_evidence_chunks_source_kind"),
        CheckConstraint(EVIDENCE_CHAR_SPAN_CHECK, name="ck_evidence_chunks_char_span"),
        CheckConstraint(EVIDENCE_TEXT_LENGTH_CHECK, name="ck_evidence_chunks_text_length"),
        CheckConstraint(
            EVIDENCE_DIMENSIONS_CHECK,
            name="ck_evidence_chunks_embedding_dimensions",
        ),
        Index(
            EVIDENCE_ORGANIZATION_CONVERSATION_INDEX,
            "organization_id",
            "conversation_id",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(MAX_SOURCE_KIND_LENGTH), nullable=False)
    source_identity: Mapped[str] = mapped_column(
        String(MAX_SOURCE_IDENTITY_LENGTH),
        nullable=False,
    )
    page_number: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    start_char: Mapped[int] = mapped_column(Integer(), nullable=False)
    end_char: Mapped[int] = mapped_column(Integer(), nullable=False)
    text: Mapped[str] = mapped_column(Text(), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(MAX_MODEL_NAME_LENGTH), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer(), nullable=False)
