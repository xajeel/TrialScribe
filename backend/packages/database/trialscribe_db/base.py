"""Shared SQLAlchemy model conventions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for tables stored in TrialScribe's application schema."""

    metadata = MetaData(schema="trialscribe", naming_convention=NAMING_CONVENTION)


class UuidPrimaryKeyMixin:
    """Give a record an application-generated UUID primary key."""

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    """Give a record database-generated timezone-aware timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrganizationScopedMixin:
    """Require tenant ownership without implementing authorization.

    Concrete domain models add an organization index and foreign key after the
    organization tenant root is introduced by the RBAC feature.
    """

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
