from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint

from trialscribe_auth.models.account import Account
from trialscribe_auth.models.session import AuthSession, RefreshToken


def constraint_names(model: type[Account | AuthSession | RefreshToken]) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def test_account_is_global_unique_and_credential_safe() -> None:
    columns = Account.__table__.columns

    assert Account.__table__.schema == "trialscribe"
    assert columns.email.nullable is False
    assert columns.password_hash.nullable is False
    assert columns.is_active.nullable is False
    assert "uq_accounts_email" in constraint_names(Account)
    assert "organization_id" not in columns
    assert "password" not in columns


def test_auth_session_has_device_lifecycle_and_account_cascade() -> None:
    columns = AuthSession.__table__.columns
    foreign_key = next(iter(columns.account_id.foreign_keys))

    assert columns.account_id.nullable is False
    assert columns.expires_at.nullable is False
    assert columns.last_refreshed_at.nullable is False
    assert columns.revoked_at.nullable is True
    assert isinstance(columns.expires_at.type, DateTime)
    assert columns.expires_at.type.timezone is True
    assert foreign_key.target_fullname == "trialscribe.accounts.id"
    assert foreign_key.ondelete == "CASCADE"
    assert "ix_auth_sessions_account_id" in {index.name for index in AuthSession.__table__.indexes}


def test_refresh_token_stores_only_hash_and_rotation_metadata() -> None:
    columns = RefreshToken.__table__.columns
    session_key = next(iter(columns.session_id.foreign_keys))
    replacement_key = next(iter(columns.replacement_token_id.foreign_keys))

    assert columns.token_hash.nullable is False
    assert columns.consumed_at.nullable is True
    assert columns.replacement_token_id.nullable is True
    assert "uq_refresh_tokens_token_hash" in constraint_names(RefreshToken)
    assert session_key.target_fullname == "trialscribe.auth_sessions.id"
    assert session_key.ondelete == "CASCADE"
    assert replacement_key.target_fullname == "trialscribe.refresh_tokens.id"
    assert replacement_key.ondelete == "SET NULL"
    assert "refresh_token" not in columns
    assert "csrf_token" not in columns
    assert "organization_id" not in columns


def test_every_authentication_foreign_key_has_a_deterministic_name() -> None:
    constraints = [
        constraint
        for table in (AuthSession.__table__, RefreshToken.__table__)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert {constraint.name for constraint in constraints} == {
        "fk_auth_sessions_account_id_accounts",
        "fk_refresh_tokens_replacement_token_id_refresh_tokens",
        "fk_refresh_tokens_session_id_auth_sessions",
    }
    assert all(
        isinstance(constraint, UniqueConstraint)
        for constraint in (Account.__table__.constraints | RefreshToken.__table__.constraints)
        if constraint.name and constraint.name.startswith("uq_")
    )
