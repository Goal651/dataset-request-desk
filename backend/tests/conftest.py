"""Shared fixtures: a real Postgres test database, one transaction per test."""

from __future__ import annotations

import os
from pathlib import Path

# Hashing dominates test time; tests do not need production-strength rounds.
os.environ.setdefault("BCRYPT_ROUNDS", "4")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import Role, User
from app.security import hash_password

settings = get_settings()
TEST_DB_URL = settings.test_database_url
SEED_CSV = Path(
    os.environ.get("SEED_CSV_PATH", Path(__file__).resolve().parents[2] / "seed" / "episodes.csv")
)

SEED_USERS: dict[str, tuple[str, Role, str, str | None]] = {
    "admin@example.com": ("admin123", Role.admin, "Ada Admin", "DroneBase"),
    "ops1@example.com": ("ops123", Role.operator, "Olu Operator", None),
    "ops2@example.com": ("ops123", Role.operator, "Odile Operator", None),
    "client-a@example.com": ("client123", Role.client, "Acme Robotics", "Acme Robotics"),
    "client-b@example.com": ("client123", Role.client, "Beta Labs", "Beta Labs"),
}


def _server_engine():
    return create_engine(
        TEST_DB_URL.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT"
    )


@pytest.fixture(scope="session")
def _test_db():
    """Create a fresh test database and migrate it to head; drop on exit."""
    server = _server_engine()
    with server.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "drd_test" WITH (FORCE)'))
        conn.execute(text('CREATE DATABASE "drd_test"'))
    server.dispose()

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(cfg, "head")
    yield

    server = _server_engine()
    with server.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "drd_test" WITH (FORCE)'))
    server.dispose()


@pytest.fixture(scope="session")
def db_engine(_test_db):
    engine = create_engine(TEST_DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """A session per test, wrapped in a transaction that is rolled back after."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """TestClient with the app's get_db overridden to the test session."""
    from app.deps import get_db
    from app.main import app

    def override_get_db():
        yield db_session  # a generator function, so FastAPI yields the session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def users(db_session):
    created = {}
    for email, (password, role, name, org) in SEED_USERS.items():
        user = User(
            email=email,
            name=name,
            role=role,
            organisation=org,
            password_hash=hash_password(password),
        )
        db_session.add(user)
        created[email] = user
    db_session.commit()
    return created


@pytest.fixture()
def login(client, users):
    """login(email) -> Authorization headers for that seed user."""

    def _login_as(email: str) -> dict[str, str]:
        response = client.post("/auth/login", json={"email": email, "password": SEED_USERS[email][0]})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login_as
