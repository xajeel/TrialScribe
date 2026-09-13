"""Persistent append-only conversation messages."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class ConversationMessage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One immutable message in a durable conversation history."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_conversation_messages_role",
        ),
        CheckConstraint(
            "char_length(btrim(content)) >= 1 AND char_length(content) <= 20000",
            name="ck_conversation_messages_content_length",
        ),
        CheckConstraint(
            "sequence > 0",
            name="ck_conversation_messages_sequence_positive",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name="fk_conversation_messages_conversation_organization",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_conversation_messages_conversation_id_sequence",
        ),
        Index(
            "ix_conversation_messages_organization_conversation_sequence",
            "organization_id",
            "conversation_id",
            "sequence",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    author_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger(), nullable=False)
