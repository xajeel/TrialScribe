from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import (
    NAMING_CONVENTION,
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)


class FoundationTestRecord(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    OrganizationScopedMixin,
    Base,
):
    __tablename__ = "foundation_test_records"
    __table_args__ = (
        CheckConstraint("length(label) > 0"),
        Index(None, "label"),
        UniqueConstraint("label"),
    )

    label: Mapped[str] = mapped_column(String(100), nullable=False)


def test_base_uses_trialscribe_schema_and_naming_convention() -> None:
    table = FoundationTestRecord.__table__

    assert table.schema == "trialscribe"
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert table.primary_key.name == "pk_foundation_test_records"
    assert next(iter(table.indexes)).name == "ix_foundation_test_records_label"
    assert next(
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ) == "uq_foundation_test_records_label"
    assert next(
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ).startswith("ck_foundation_test_records_")


def test_uuid_and_organization_columns_are_required() -> None:
    table = FoundationTestRecord.__table__

    assert table.c.id.primary_key is True
    assert table.c.id.default is not None
    assert table.c.id.default.is_callable is True
    assert table.c.organization_id.nullable is False
    assert table.c.organization_id.foreign_keys == set()


def test_timestamps_are_timezone_aware_and_database_generated() -> None:
    table = FoundationTestRecord.__table__

    assert table.c.created_at.type.timezone is True
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.type.timezone is True
    assert table.c.updated_at.server_default is not None
    assert table.c.updated_at.onupdate is not None
