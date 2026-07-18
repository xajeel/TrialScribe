"""Public account request and response contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from trialscribe_auth.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
)
from trialscribe_auth.services.accounts import InvalidAccountInput, normalize_email


class RegisterRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        try:
            return normalize_email(value)
        except InvalidAccountInput as error:
            raise ValueError(str(error)) from None

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
            raise ValueError(
                f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters"
            )
        return value


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    is_active: bool
    created_at: datetime
