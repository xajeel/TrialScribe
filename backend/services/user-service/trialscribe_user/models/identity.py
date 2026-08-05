"""Durable organization associations for privacy-safe account identity lookup."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class OrganizationIdentityLink(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Record that an account may be identified inside one organization.

    This historical association never grants organization access. Authorization
    continues to use current memberships exclusively.
    """

    __tablename__ = "organization_identity_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "account_id",
            name="uq_organization_identity_links_organization_id_account_id",
        ),
        Index("ix_organization_identity_links_organization_id", "organization_id"),
        Index("ix_organization_identity_links_account_id", "account_id"),
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
