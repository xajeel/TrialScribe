"""Persistent account identity owned by authentication."""

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Account(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A global login identity that can join multiple organizations."""

    __tablename__ = "accounts"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
