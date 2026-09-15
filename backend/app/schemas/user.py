"""
backend/app/schemas/user.py
User model schema for auth and document ownership.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    """User record stored in DB."""
    user_id: str = Field(..., description="UUID user identifier")
    username: str = Field(..., description="Unique username")
    email: str = Field(..., description="User email")
    hashed_password: str = Field(..., description="Bcrypt-hashed password")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserPublic(BaseModel):
    """Public user info (safe to return in API)."""
    user_id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime
