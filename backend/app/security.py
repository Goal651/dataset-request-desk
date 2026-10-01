"""Password hashing (bcrypt) and JWT access tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "jti": f"{user_id}-{now.timestamp():.0f}",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    pass


def decode_access_token(token: str) -> tuple[int, str]:
    """Return (user_id, role) from a valid token; raise TokenError otherwise."""
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired token") from exc
    try:
        return int(claims["sub"]), str(claims["role"])
    except (KeyError, ValueError) as exc:
        raise TokenError("Malformed token claims") from exc
