"""Persistent access grants for shared conversations."""

from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class ConversationAccess(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One organization member's access to one conversation."""

    __tablename__ = "conversation_access"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["trialscribe.conversations.id", "trialscribe.conversations.organization_id"],
            name="fk_conversation_access_conversation_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "account_id"],
            [
                "trialscribe.organization_memberships.organization_id",
                "trialscribe.organization_memberships.account_id",
            ],
            name="fk_conversation_access_organization_membership",
            ondelete="CASCADE",
            use_alter=True,
        ),
        UniqueConstraint(
            "conversation_id",
            "account_id",
            name="uq_conversation_access_conversation_id_account_id",
        ),
        Index(
            "ix_conversation_access_organization_account",
            "organization_id",
            "account_id",
            "conversation_id",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    account_id: Mapped[UUID] = mapped_column(nullable=False)
