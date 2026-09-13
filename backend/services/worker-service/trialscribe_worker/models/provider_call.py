"""One metered call through the provider gateway."""

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

from trialscribe_worker.utils.constant import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    MAX_MODEL_NAME_LENGTH,
    MAX_PRICING_VERSION_LENGTH,
    MAX_PROVIDER_NAME_LENGTH,
    MAX_PROVIDER_OPERATION_LENGTH,
    MAX_PROVIDER_OUTCOME_LENGTH,
    PROVIDER_CALL_CACHE_HIT_TOKENS_CHECK,
    PROVIDER_CALL_COST_MICROS_CHECK,
    PROVIDER_CALL_INPUT_TOKENS_CHECK,
    PROVIDER_CALL_LATENCY_CHECK,
    PROVIDER_CALL_OPERATION_CHECK,
    PROVIDER_CALL_ORGANIZATION_JOB_INDEX,
    PROVIDER_CALL_OUTCOME_CHECK,
    PROVIDER_CALL_OUTPUT_TOKENS_CHECK,
    PROVIDER_CALL_SUCCEEDED_IDEMPOTENCY_INDEX,
)


class ProviderCall(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A single provider attempt, attributed to a tenant, job, and account.

    Foreign keys to jobs, conversations, accounts, and organizations live in
    migration `0012_provider_calls`. Those tables belong to other packages.
    """

    __tablename__ = "provider_calls"
    __table_args__ = (
        CheckConstraint(PROVIDER_CALL_OPERATION_CHECK, name="ck_provider_calls_operation"),
        CheckConstraint(PROVIDER_CALL_OUTCOME_CHECK, name="ck_provider_calls_outcome"),
        CheckConstraint(
            PROVIDER_CALL_INPUT_TOKENS_CHECK,
            name="ck_provider_calls_input_tokens",
        ),
        CheckConstraint(
            PROVIDER_CALL_OUTPUT_TOKENS_CHECK,
            name="ck_provider_calls_output_tokens",
        ),
        CheckConstraint(
            PROVIDER_CALL_CACHE_HIT_TOKENS_CHECK,
            name="ck_provider_calls_cache_hit_tokens",
        ),
        CheckConstraint(
            PROVIDER_CALL_COST_MICROS_CHECK,
            name="ck_provider_calls_cost_micros",
        ),
        CheckConstraint(PROVIDER_CALL_LATENCY_CHECK, name="ck_provider_calls_latency_ms"),
        Index(
            PROVIDER_CALL_ORGANIZATION_JOB_INDEX,
            "organization_id",
            "job_id",
            "created_at",
            "id",
        ),
        Index(
            PROVIDER_CALL_SUCCEEDED_IDEMPOTENCY_INDEX,
            "idempotency_key",
            unique=True,
            postgresql_where=text("outcome = 'succeeded'"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    job_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    account_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(MAX_IDEMPOTENCY_KEY_LENGTH),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(MAX_PROVIDER_NAME_LENGTH), nullable=False)
    operation: Mapped[str] = mapped_column(
        String(MAX_PROVIDER_OPERATION_LENGTH),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(MAX_MODEL_NAME_LENGTH), nullable=False)
    pricing_version: Mapped[str] = mapped_column(
        String(MAX_PRICING_VERSION_LENGTH),
        nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(Integer(), nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer(), nullable=False)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer(), nullable=False)
    cost_micros: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer(), nullable=False)
    outcome: Mapped[str] = mapped_column(String(MAX_PROVIDER_OUTCOME_LENGTH), nullable=False)
