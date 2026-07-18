"""Public organization and membership contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

OrganizationRole = Literal["owner", "admin", "member"]


class OrganizationCreateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 120:
            raise ValueError("Organization name must be 1 to 120 characters")
        return normalized


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    role: OrganizationRole
    created_at: datetime


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    account_id: UUID
    role: OrganizationRole
    created_at: datetime


class MembershipRoleUpdateRequest(BaseModel):
    role: OrganizationRole
