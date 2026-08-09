"""The durable ticket that records one piece of background work.

The tenant, account, and conversation columns are enforced by foreign keys in
migration `0010_jobs`, which owns the schema, but they are declared here as plain
columns. The tables they point at belong to other services' packages, and a
service never imports another service's application package — so this model
cannot see them, and a foreign key declared here would fail to resolve.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_worker.utils.constant import (
    JOB_ATTEMPT_CHECK,
    JOB_COMPLETION_CHECK,
    JOB_ERROR_CODE_CHECK,
    JOB_ORGANIZATION_STATUS_INDEX,
    JOB_PROGRESS_CHECK,
    JOB_STATUS_CHECK,
    MAX_JOB_ERROR_CODE_LENGTH,
    MAX_JOB_KIND_LENGTH,
    MAX_JOB_STATUS_LENGTH,
)


class Job(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One request for background work, and the single outcome it ends with.

    Every status change is a conditional update that names the status it expects
    to find, so a redelivered event or a second worker changes nothing.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(JOB_STATUS_CHECK, name="ck_jobs_status"),
        CheckConstraint(JOB_ERROR_CODE_CHECK, name="ck_jobs_error_code"),
        CheckConstraint(JOB_PROGRESS_CHECK, name="ck_jobs_progress_range"),
        CheckConstraint(JOB_ATTEMPT_CHECK, name="ck_jobs_attempt_nonnegative"),
        CheckConstraint(JOB_COMPLETION_CHECK, name="ck_jobs_completion_state"),
        Index(
            JOB_ORGANIZATION_STATUS_INDEX,
            "organization_id",
            "status",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    requested_by_account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(MAX_JOB_KIND_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(
        String(MAX_JOB_STATUS_LENGTH),
        nullable=False,
        default="queued",
    )
    attempt: Mapped[int] = mapped_column(SmallInteger(), nullable=False, default=0)
    progress: Mapped[int] = mapped_column(SmallInteger(), nullable=False, default=0)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB(),
        nullable=False,
        default=dict,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(MAX_JOB_ERROR_CODE_LENGTH),
        nullable=True,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
