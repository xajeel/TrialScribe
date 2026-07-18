"""Authentication claims trusted by the user service."""

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
