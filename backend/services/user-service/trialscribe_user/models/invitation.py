"""Persistent single-use organization invitations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Invitation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A hash-only invitation granting one organization membership."""

    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'member')",
            name="ck_organization_invitations_role",
        ),
        Index("ix_organization_invitations_organization_id", "organization_id"),
        Index("ix_organization_invitations_invited_by_account_id", "invited_by_account_id"),
        Index(
            "uq_organization_invitations_pending_email",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("trialscribe.organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    invited_by_account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="CASCADE",
            use_alter=True,
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
