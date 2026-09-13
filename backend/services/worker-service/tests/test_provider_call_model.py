from pathlib import Path

from sqlalchemy import CheckConstraint

from trialscribe_worker.models.provider_call import ProviderCall
from trialscribe_worker.utils.constant import (
    PROVIDER_CALL_ORGANIZATION_JOB_INDEX,
    PROVIDER_CALL_SUCCEEDED_IDEMPOTENCY_INDEX,
)
from trialscribe_worker.utils.enum import ProviderOperation, ProviderOutcome


def check_constraint(name: str) -> str:
    for constraint in ProviderCall.__table__.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return str(constraint.sqltext)
    raise AssertionError(f"missing check constraint {name}")


def test_provider_calls_table_is_registered() -> None:
    assert ProviderCall.__tablename__ == "provider_calls"
    assert ProviderCall.__table__.schema == "trialscribe"
    assert [column.name for column in ProviderCall.__table__.primary_key] == ["id"]


def test_every_operation_and_outcome_is_accepted() -> None:
    operation_check = check_constraint("ck_provider_calls_operation")
    outcome_check = check_constraint("ck_provider_calls_outcome")
    for operation in ProviderOperation:
        assert f"'{operation.value}'" in operation_check
    for outcome in ProviderOutcome:
        assert f"'{outcome.value}'" in outcome_check


def test_token_and_cost_columns_cannot_go_negative() -> None:
    assert "input_tokens >= 0" in check_constraint("ck_provider_calls_input_tokens")
    assert "output_tokens >= 0" in check_constraint("ck_provider_calls_output_tokens")
    assert "cache_hit_tokens >= 0" in check_constraint("ck_provider_calls_cache_hit_tokens")
    assert "cost_micros >= 0" in check_constraint("ck_provider_calls_cost_micros")
    assert "latency_ms >= 0" in check_constraint("ck_provider_calls_latency_ms")


def test_the_model_declares_no_foreign_key_it_cannot_resolve() -> None:
    declared = [
        column.name for column in ProviderCall.__table__.columns if column.foreign_keys
    ]
    assert declared == []


def test_succeeded_idempotency_keys_are_unique() -> None:
    indexes = {index.name: index for index in ProviderCall.__table__.indexes}
    succeeded = indexes[PROVIDER_CALL_SUCCEEDED_IDEMPOTENCY_INDEX]
    assert succeeded.unique is True
    assert [column.name for column in succeeded.columns] == ["idempotency_key"]


def test_calls_are_indexed_for_job_scoped_listing() -> None:
    indexes = {index.name: index for index in ProviderCall.__table__.indexes}
    listing = indexes[PROVIDER_CALL_ORGANIZATION_JOB_INDEX]
    assert [column.name for column in listing.columns] == [
        "organization_id",
        "job_id",
        "created_at",
        "id",
    ]


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "database"
    / "migrations"
    / "versions"
    / "0012_create_provider_calls_table.py"
)


def test_the_migration_keeps_calls_inside_their_tenant() -> None:
    source = MIGRATION.read_text()
    assert "fk_provider_calls_organization_id_organizations" in source
    assert "fk_provider_calls_conversation_organization" in source
    assert "fk_provider_calls_job_id_jobs" in source
    assert "fk_provider_calls_account_id_accounts" in source
    assert "uq_provider_calls_succeeded_idempotency" in source
