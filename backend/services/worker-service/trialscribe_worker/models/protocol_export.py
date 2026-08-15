"""A stored ICH M11 Word export for one conversation job."""

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_worker.utils.constant import (
    EXPORT_BYTE_SIZE_CHECK,
    EXPORT_FILENAME_CHECK,
    EXPORT_SCOPE_CHECK,
    EXPORT_SCOPE_INDEX,
    EXPORT_SECTION_COUNT_CHECK,
    MAX_EXPORT_FILENAME_LENGTH,
)


class ProtocolExport(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """The assembled Word bytes from one export_protocol job.

    Foreign keys to conversations, jobs, and accounts live in migration
    `0017_protocol_exports`. Those tables belong to other packages.
    """

    __tablename__ = "protocol_exports"
    __table_args__ = (
        CheckConstraint(EXPORT_SCOPE_CHECK, name="ck_protocol_exports_scope"),
        CheckConstraint(EXPORT_BYTE_SIZE_CHECK, name="ck_protocol_exports_byte_size"),
        CheckConstraint(
            EXPORT_SECTION_COUNT_CHECK,
            name="ck_protocol_exports_section_count",
        ),
        CheckConstraint(EXPORT_FILENAME_CHECK, name="ck_protocol_exports_filename"),
        Index(
            EXPORT_SCOPE_INDEX,
            "organization_id",
            "conversation_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(Text(), nullable=False)
    filename: Mapped[str] = mapped_column(String(MAX_EXPORT_FILENAME_LENGTH), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    section_count: Mapped[int] = mapped_column(Integer(), nullable=False)
