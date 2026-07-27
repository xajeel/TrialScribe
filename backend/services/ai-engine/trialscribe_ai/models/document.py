"""Persistent uploaded documents attached to a conversation."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Document(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A validated trial-data or research document stored under a conversation."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('trial_data', 'research_document')",
            name="ck_documents_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "byte_size > 0",
            name="ck_documents_byte_size_positive",
        ),
        CheckConstraint(
            "char_length(btrim(filename)) >= 1 AND char_length(filename) <= 255",
            name="ck_documents_filename_length",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name="fk_documents_conversation_organization",
            ondelete="CASCADE",
        ),
        Index(
            "ix_documents_organization_conversation_created",
            "organization_id",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    uploaded_by_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    content: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
