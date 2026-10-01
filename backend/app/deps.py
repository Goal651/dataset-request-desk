"""Shared FastAPI dependencies: DB session, auth, current user, role gates."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Role, User
from app.security import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    """One session per request, stored on request.state so middleware can use it too.

    Committed on success, rolled back on any error.
    """
    db = SessionLocal()
    request.state.db = db
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    """Resolve the JWT bearer token to an active user, or 401."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        user_id, _role = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or deactivated user")
    request.state.user = user  # middleware logs the user id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role):
    """Dependency factory: allow only the given roles.

    Admin can do everything an operator can, so any operator gate admits admins.
    """

    def dependency(user: CurrentUser) -> User:
        allowed = set(roles) | ({Role.admin} if Role.operator in roles else set())
        if user.role not in allowed:
            names = " or ".join(sorted(r.value for r in allowed))
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {names}")
        return user

    return dependency
