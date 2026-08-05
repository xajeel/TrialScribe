"""Public tenant-scoped account identity contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationIdentitySummary(BaseModel):
    account_id: UUID
    email: str
    is_active: bool


class IdentityResolutionRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    account_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("account_ids")
    @classmethod
    def reject_duplicates(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Account IDs must be unique")
        return value
