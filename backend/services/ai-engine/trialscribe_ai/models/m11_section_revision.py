"""Append-only snapshots of ICH M11 section changes."""

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


class M11SectionRevision(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One immutable post-action snapshot of an M11 section."""

    __tablename__ = "m11_section_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_m11_section_revisions_number_positive",
        ),
        CheckConstraint(
            "action IN ('revised', 'done', 'reopened', 'generated', 'restored')",
            name="ck_m11_section_revisions_action",
        ),
        CheckConstraint(
            "status IN ('draft', 'done')",
            name="ck_m11_section_revisions_status",
        ),
        CheckConstraint(
            "(action = 'done' AND status = 'done') "
            "OR (action IN ('revised', 'reopened', 'generated', 'restored') "
            "AND status = 'draft')",
            name="ck_m11_section_revisions_action_status",
        ),
        CheckConstraint(
            "char_length(instructions) <= 20000",
            name="ck_m11_section_revisions_instructions_length",
        ),
        CheckConstraint(
            "char_length(content) <= 200000",
            name="ck_m11_section_revisions_content_length",
        ),
        ForeignKeyConstraint(
            ["section_id", "conversation_id", "organization_id"],
            [
                "trialscribe.m11_sections.id",
                "trialscribe.m11_sections.conversation_id",
                "trialscribe.m11_sections.organization_id",
            ],
            name="fk_m11_section_revisions_section_conversation_organization",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "section_id",
            "revision_number",
            name="uq_m11_section_revisions_section_revision",
        ),
        Index(
            "ix_m11_section_revisions_scope_revision",
            "organization_id",
            "conversation_id",
            "section_id",
            "revision_number",
        ),
    )

    section_id: Mapped[UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    revision_number: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    instructions: Mapped[str] = mapped_column(Text(), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    author_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
