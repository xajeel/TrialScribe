"""A persisted protocol readiness snapshot for one conversation check."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_worker.utils.constant import READINESS_SCOPE_INDEX


class ProtocolReadinessCheck(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """The scored snapshot from one validate_readiness job.

    Foreign keys to jobs and conversations live in migration
    `0016_protocol_readiness_checks`. Those tables belong to other packages.
    """

    __tablename__ = "protocol_readiness_checks"
    __table_args__ = (
        Index(
            READINESS_SCOPE_INDEX,
            "organization_id",
            "conversation_id",
            "computed_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ready: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    protocol_title: Mapped[str] = mapped_column(Text(), nullable=False)
    summary: Mapped[dict[str, object]] = mapped_column(JSONB(), nullable=False)
    issues: Mapped[list[object]] = mapped_column(JSONB(), nullable=False)
    sections: Mapped[list[object]] = mapped_column(JSONB(), nullable=False)
