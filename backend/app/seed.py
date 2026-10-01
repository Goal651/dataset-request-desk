"""Seed users from seed/users.json (idempotent: upsert by email)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Role, User
from app.security import hash_password

DEFAULT_SEED_USERS_PATH = Path(__file__).resolve().parents[2] / "seed" / "users.json"


def seed_users(session: Session, users_path: Path | None = None) -> int:
    """Create or update seed users. Safe to run repeatedly."""
    path = Path(users_path or os.environ.get("SEED_USERS_PATH", DEFAULT_SEED_USERS_PATH))
    data = json.loads(path.read_text())
    count = 0
    for entry in data:
        email = entry["email"].lower()
        user = session.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email)
            session.add(user)
        user.name = entry["name"]
        user.role = Role(entry["role"])
        user.organisation = entry.get("organisation")
        user.password_hash = hash_password(entry["password"])
        user.is_active = True
        count += 1
    session.commit()
    return count


if __name__ == "__main__":
    from app.db import SessionLocal

    created = seed_users(SessionLocal())
    print(f"seeded {created} users")
