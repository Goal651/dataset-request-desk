"""User management (admin only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.deps import DbSession, require_role
from app.models import Role, User
from app.routers.auth import UserOut, to_user_out
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    role: Role
    organisation: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserUpdateIn(BaseModel):
    is_active: bool | None = None
    role: Role | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


@router.get("", response_model=list[UserOut])
def list_users(
    _admin: Annotated[User, Depends(require_role(Role.admin))],
    db: DbSession,
) -> list[UserOut]:
    return [to_user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateIn,
    admin: Annotated[User, Depends(require_role(Role.admin))],
    db: DbSession,
) -> UserOut:
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(
        email=payload.email.lower(),
        name=payload.name,
        role=payload.role,
        organisation=payload.organisation,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    return to_user_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdateIn,
    admin: Annotated[User, Depends(require_role(Role.admin))],
    db: DbSession,
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None and user.id == admin.id and payload.role != Role.admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot demote yourself")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(status.HTTP_409_CONFLICT, "You cannot deactivate yourself")
        user.is_active = payload.is_active
    return to_user_out(user)
