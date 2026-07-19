"""Account registration use cases."""

from email_validator import EmailNotValidError, validate_email

from trialscribe_auth.models.account import Account
from trialscribe_auth.repositories.accounts import (
    AccountRepository,
    DuplicateAccountError,
)
from trialscribe_auth.security.passwords import hash_password
from trialscribe_auth.utils.exceptions import AccountConflictError, InvalidAccountInput


def normalize_email(email: str) -> str:
    """Return one comparison-safe representation without a DNS lookup."""

    try:
        result = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError:
        raise InvalidAccountInput("Email address is invalid") from None
    return result.normalized.casefold()


class AccountService:
    """Register global identities through an injected transaction repository."""

    def __init__(self, repository: AccountRepository) -> None:
        self._repository = repository

    async def register_account(self, email: str, password: str) -> Account:
        normalized_email = normalize_email(email)
        try:
            password_hash = hash_password(password)
        except ValueError as error:
            raise InvalidAccountInput(str(error)) from None

        account = Account(email=normalized_email, password_hash=password_hash)
        try:
            return await self._repository.add(account)
        except DuplicateAccountError:
            raise AccountConflictError("Account could not be created") from None
