"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.deps import CurrentUser, DbSession
from app.models import Role, User
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: Role
    organisation: str | None = None

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: DbSession) -> TokenOut:
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account is deactivated")
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value),
        user=to_user_out(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return to_user_out(user)
