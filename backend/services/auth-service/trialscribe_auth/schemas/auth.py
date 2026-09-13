"""Authentication token request and response contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AccessClaims(BaseModel):
    """Strict claims carried by a TrialScribe access token."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    sub: UUID
    iss: str
    aud: str
    iat: datetime
    nbf: datetime
    exp: datetime
    jti: UUID
    type: Literal["access"]


class TokenResponse(BaseModel):
    """Short-lived access credentials returned to API clients."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    """Email and password submitted to the login endpoint."""

    model_config = ConfigDict(hide_input_in_errors=True)

    email: str
    password: str
