from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trialscribe_auth.models.account import Account
from trialscribe_auth.repositories.accounts import DuplicateAccountError
from trialscribe_auth.schemas.account import AccountResponse, RegisterRequest
from trialscribe_auth.security.passwords import dummy_verify, hash_password, verify_password
from trialscribe_auth.services.accounts import (
    AccountConflictError,
    AccountService,
    InvalidAccountInput,
    normalize_email,
)


class FakeAccountRepository:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.added: Account | None = None

    async def add(self, account: Account) -> Account:
        if self.duplicate:
            raise DuplicateAccountError("database constraint details")
        account.id = uuid4()
        account.is_active = True
        account.created_at = datetime.now(UTC)
        account.updated_at = account.created_at
        self.added = account
        return account


@pytest.mark.parametrize(
    ("input_email", "expected"),
    [
        ("Person@Example.COM", "person@example.com"),
        (" person@example.com ", "person@example.com"),
        ("USER+Research@Example.com", "user+research@example.com"),
    ],
)
def test_email_is_normalized_for_comparison(input_email: str, expected: str) -> None:
    assert normalize_email(input_email) == expected


@pytest.mark.parametrize("email", ["", "not-an-email", "name@localhost"])
def test_invalid_email_has_a_stable_public_error(email: str) -> None:
    with pytest.raises(InvalidAccountInput, match="Email address is invalid"):
        normalize_email(email)


@pytest.mark.parametrize(
    "password",
    [
        "fifteen-chars!!",
        "correct horse battery staple",
        "安全な長いパスフレーズです安全です",
        "x" * 128,
    ],
)
def test_password_hashes_are_argon2id_and_verify(password: str) -> None:
    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert password not in password_hash
    assert verify_password(password, password_hash) is True
    assert verify_password(f"{password}wrong", password_hash) is False


@pytest.mark.parametrize("password", ["x" * 14, "x" * 129])
def test_password_length_boundaries_do_not_truncate(password: str) -> None:
    with pytest.raises(ValueError, match="15 to 128"):
        hash_password(password)


def test_dummy_verification_accepts_arbitrary_input_without_returning_a_hash() -> None:
    assert dummy_verify("attacker supplied password") is None


@pytest.mark.anyio
async def test_registration_persists_only_normalized_email_and_hash() -> None:
    repository = FakeAccountRepository()
    service = AccountService(repository)  # type: ignore[arg-type]
    password = "a long research passphrase"

    account = await service.register_account("Researcher@Example.COM", password)

    assert account.email == "researcher@example.com"
    assert account.password_hash != password
    assert verify_password(password, account.password_hash) is True
    response = AccountResponse.model_validate(account).model_dump()
    assert "password" not in response
    assert "password_hash" not in response


@pytest.mark.anyio
async def test_duplicate_race_becomes_a_safe_conflict() -> None:
    repository = FakeAccountRepository(duplicate=True)
    service = AccountService(repository)  # type: ignore[arg-type]

    with pytest.raises(AccountConflictError) as captured:
        await service.register_account(
            "researcher@example.com",
            "a long research passphrase",
        )

    assert str(captured.value) == "Account could not be created"
    assert "database" not in str(captured.value)


def test_registration_schema_validates_boundaries_without_echoing_password() -> None:
    password = "short"

    with pytest.raises(ValidationError) as captured:
        RegisterRequest(email="researcher@example.com", password=password)

    assert password not in str(captured.value)


def test_account_response_never_declares_credential_fields() -> None:
    account = Account(
        id=uuid4(),
        email="researcher@example.com",
        password_hash="secret-hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert set(AccountResponse.model_validate(account).model_dump()) == {
        "id",
        "email",
        "is_active",
        "created_at",
    }
