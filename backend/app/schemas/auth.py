"""Auth request/response schemas.

Kept separate from ORM models: these define the wire contract, the models
define storage. `UserRead` never exposes the password hash.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    """Self-service sign-up always creates a candidate.

    There is deliberately no `role` field: when there was one, anyone could
    register as a recruiter and read every candidate's answers. Recruiter
    accounts are created with `python -m app.cli create-recruiter`.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime
