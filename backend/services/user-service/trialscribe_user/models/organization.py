"""Persistent organization tenant roots."""

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Organization(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A workspace whose access is controlled by memberships."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "name = btrim(name) AND char_length(name) BETWEEN 1 AND 120",
            name="ck_organizations_name_length",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
