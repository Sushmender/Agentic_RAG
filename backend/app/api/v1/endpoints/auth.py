"""
backend/app/api/v1/endpoints/auth.py
User registration and login endpoints.
POST /auth/register
POST /auth/login
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends

from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.query import UserRegisterRequest, TokenResponse
from app.schemas.user import UserPublic

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# In-memory user store for Day 0/1 — replaced by SQLite in Day 7
_users: dict[str, dict] = {}  # username → user dict


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(request: UserRegisterRequest) -> UserPublic:
    """Create a new user account. Returns public user info."""
    import uuid
    from datetime import datetime, timezone

    if request.username in _users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{request.username}' already exists.",
        )

    user_id = str(uuid.uuid4())
    user = {
        "user_id": user_id,
        "username": request.username,
        "email": request.email,
        "hashed_password": hash_password(request.password),
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    _users[request.username] = user

    logger.info("User registered", user_id=user_id, username=request.username)
    return UserPublic(**user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and get JWT access token",
)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Authenticate with username+password, return JWT Bearer token."""
    user = _users.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user["is_active"]:
        raise HTTPException(status_code=400, detail="Inactive user.")

    token = create_access_token(subject=user["user_id"])
    logger.info("User logged in", user_id=user["user_id"], username=user["username"])

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user["user_id"],
        username=user["username"],
    )
