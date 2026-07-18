"""Public organization invitation contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

InvitationRole = Literal["admin", "member"]


class InvitationCreateRequest(BaseModel):
    email: str
    role: InvitationRole


class InvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    token: str = Field(min_length=1, max_length=512)


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    email: str
    role: InvitationRole
    invited_by_account_id: UUID
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreatedResponse(InvitationResponse):
    accept_url: str
