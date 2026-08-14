"""One recorded attempt to draft an M11 section, including the prompt used."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_worker.utils.constant import (
    GENERATION_ATTEMPT_ATTEMPT_CHECK,
    GENERATION_ATTEMPT_ERROR_CHECK,
    GENERATION_ATTEMPT_INDEX,
    GENERATION_ATTEMPT_STATUS_CHECK,
    MAX_JOB_ERROR_CODE_LENGTH,
    MAX_MODEL_NAME_LENGTH,
)


class SectionGenerationAttempt(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """The prompt, outcome, and citations for one section in one job attempt.

    Foreign keys to jobs and conversations live in migration
    `0014_section_generation_attempts`. Those tables belong to other packages.
    """

    __tablename__ = "section_generation_attempts"
    __table_args__ = (
        CheckConstraint(
            GENERATION_ATTEMPT_STATUS_CHECK,
            name="ck_section_generation_attempts_status",
        ),
        CheckConstraint(
            GENERATION_ATTEMPT_ERROR_CHECK,
            name="ck_section_generation_attempts_error_code",
        ),
        CheckConstraint(
            GENERATION_ATTEMPT_ATTEMPT_CHECK,
            name="ck_section_generation_attempts_attempt",
        ),
        Index(
            GENERATION_ATTEMPT_INDEX,
            "organization_id",
            "conversation_id",
            "job_id",
            "section_number",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer(), nullable=False)
    section_number: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str | None] = mapped_column(String(MAX_MODEL_NAME_LENGTH), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    content: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(
        String(MAX_JOB_ERROR_CODE_LENGTH),
        nullable=True,
    )
    citation_ids: Mapped[list[str]] = mapped_column(
        JSONB(),
        nullable=False,
        default=list,
    )
