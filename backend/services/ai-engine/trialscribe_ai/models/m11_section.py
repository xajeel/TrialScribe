"""Persistent ICH M11 sections attached to a conversation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class M11Section(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """The current authoring state of one top-level M11 section."""

    __tablename__ = "m11_sections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'done')",
            name="ck_m11_sections_status",
        ),
        CheckConstraint(
            "current_revision >= 0",
            name="ck_m11_sections_current_revision_nonnegative",
        ),
        CheckConstraint(
            "section_number = btrim(section_number) "
            "AND char_length(section_number) BETWEEN 1 AND 8",
            name="ck_m11_sections_number_length",
        ),
        CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 200",
            name="ck_m11_sections_title_length",
        ),
        CheckConstraint(
            "char_length(instructions) <= 20000",
            name="ck_m11_sections_instructions_length",
        ),
        CheckConstraint(
            "char_length(content) <= 200000",
            name="ck_m11_sections_content_length",
        ),
        CheckConstraint(
            "(status = 'draft' AND completed_at IS NULL "
            "AND completed_by_account_id IS NULL) "
            "OR (status = 'done' AND completed_at IS NOT NULL)",
            name="ck_m11_sections_completion_state",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name="fk_m11_sections_conversation_organization",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id",
            "conversation_id",
            "organization_id",
            name="uq_m11_sections_id_conversation_organization",
        ),
        UniqueConstraint(
            "conversation_id",
            "organization_id",
            "section_number",
            name="uq_m11_sections_conversation_number",
        ),
        UniqueConstraint(
            "conversation_id",
            "organization_id",
            "position",
            name="uq_m11_sections_conversation_position",
        ),
        Index(
            "ix_m11_sections_organization_conversation_position",
            "organization_id",
            "conversation_id",
            "position",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    section_number: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    instructions: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    current_revision: Mapped[int] = mapped_column(
        BigInteger(),
        nullable=False,
        default=0,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_by_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
