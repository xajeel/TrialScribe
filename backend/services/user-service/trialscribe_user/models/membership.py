"""Persistent organization memberships and roles."""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Membership(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One account's current role in one organization."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'member')",
            name="ck_organization_memberships_role",
        ),
        UniqueConstraint(
            "organization_id",
            "account_id",
            name="uq_organization_memberships_organization_id_account_id",
        ),
        Index("ix_organization_memberships_organization_id", "organization_id"),
        Index("ix_organization_memberships_account_id", "account_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("trialscribe.organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trialscribe.accounts.id",
            ondelete="CASCADE",
            use_alter=True,
        ),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
