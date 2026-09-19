"""Request/response schemas for the first-party auth API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)  # policy enforced server-side
    display_name: str | None = Field(default=None, max_length=200)


class SigninRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class GenericMessage(BaseModel):
    """Deliberately non-committal payload for enumeration-safe flows."""

    message: str


class SessionUser(BaseModel):
    """The current authenticated identity (never includes credentials)."""

    id: uuid.UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    email_verified: bool
