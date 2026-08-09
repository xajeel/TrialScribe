from pathlib import Path

from sqlalchemy import CheckConstraint

from trialscribe_worker.models.job import Job
from trialscribe_worker.utils.constant import JOB_ORGANIZATION_STATUS_INDEX
from trialscribe_worker.utils.enum import (
    CLAIMABLE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    JobErrorCode,
    JobStatus,
)


def check_constraint(name: str) -> str:
    for constraint in Job.__table__.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return str(constraint.sqltext)
    raise AssertionError(f"missing check constraint {name}")


def test_jobs_table_is_registered_in_the_application_schema() -> None:
    assert Job.__tablename__ == "jobs"
    assert Job.__table__.schema == "trialscribe"
    assert [column.name for column in Job.__table__.primary_key] == ["id"]


def test_every_status_and_error_code_is_accepted_by_the_database() -> None:
    status_check = check_constraint("ck_jobs_status")
    error_check = check_constraint("ck_jobs_error_code")

    for status in JobStatus:
        assert f"'{status.value}'" in status_check
    for code in JobErrorCode:
        assert f"'{code.value}'" in error_check


def test_a_job_is_finished_exactly_when_it_reached_a_terminal_status() -> None:
    completion_check = check_constraint("ck_jobs_completion_state")

    for status in TERMINAL_JOB_STATUSES:
        assert f"'{status.value}'" in completion_check
    for status in CLAIMABLE_JOB_STATUSES:
        assert f"'{status.value}'" in completion_check
    assert "finished_at IS NOT NULL" in completion_check
    assert "finished_at IS NULL" in completion_check


def test_progress_and_attempt_stay_inside_their_bounds() -> None:
    assert "progress BETWEEN 0 AND 100" in check_constraint("ck_jobs_progress_range")
    assert "attempt >= 0" in check_constraint("ck_jobs_attempt_nonnegative")


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "database"
    / "migrations"
    / "versions"
    / "0010_create_jobs_table.py"
)


def test_the_model_declares_no_foreign_key_it_cannot_resolve() -> None:
    """Tenancy is enforced by the migration, not by this package's metadata.

    `organizations`, `accounts`, and `conversations` are owned by other services'
    packages, which this one may not import. A foreign key declared on the model
    would therefore fail to resolve the moment a statement is built.
    """

    declared = [
        column.name for column in Job.__table__.columns if column.foreign_keys
    ]

    assert declared == []


def test_the_migration_keeps_a_job_inside_its_own_organization() -> None:
    source = MIGRATION.read_text()

    assert "fk_jobs_conversation_organization" in source
    assert '["conversation_id", "organization_id"]' in source
    assert "trialscribe.conversations.organization_id" in source
    assert "fk_jobs_organization_id_organizations" in source
    assert "fk_jobs_requested_by_account_id_accounts" in source


def test_jobs_are_indexed_for_tenant_scoped_listing() -> None:
    index = {index.name: index for index in Job.__table__.indexes}

    assert JOB_ORGANIZATION_STATUS_INDEX in index
    assert [column.name for column in index[JOB_ORGANIZATION_STATUS_INDEX].columns] == [
        "organization_id",
        "status",
        "created_at",
        "id",
    ]


def test_statuses_are_split_into_claimable_and_terminal_without_overlap() -> None:
    assert CLAIMABLE_JOB_STATUSES.isdisjoint(TERMINAL_JOB_STATUSES)
    assert CLAIMABLE_JOB_STATUSES | TERMINAL_JOB_STATUSES == set(JobStatus)
    assert JobStatus.SUCCEEDED.is_terminal() is True
    assert JobStatus.RUNNING.is_terminal() is False
