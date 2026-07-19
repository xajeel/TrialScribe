"""Persistent conversation workspace roots."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Conversation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A durable, organization-scoped authoring conversation."""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 120",
            name="ck_conversations_title_length",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_conversations_id_organization_id",
        ),
        Index(
            "ix_conversations_organization_archive_activity",
            "organization_id",
            "archived_at",
            "last_activity_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trialscribe.organizations.id",
            ondelete="CASCADE",
            use_alter=True,
        ),
        nullable=False,
    )
    owner_account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="CASCADE",
            use_alter=True,
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
