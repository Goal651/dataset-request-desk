"""Auth + role-based authorization tests."""

from __future__ import annotations


def test_login_success_returns_token(client, users):
    response = client.post(
        "/auth/login", json={"email": "ops1@example.com", "password": "ops123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "operator"


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/auth/login", json={"email": "ops1@example.com", "password": "nope"}
    )
    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_returns_current_user(client, login):
    me = client.get("/auth/me", headers=login("client-a@example.com"))
    assert me.status_code == 200
    assert me.json()["email"] == "client-a@example.com"


def test_invalid_token_rejected(client):
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------- role gates


def test_client_cannot_list_all_users(client, login):
    response = client.get("/users", headers=login("client-a@example.com"))
    assert response.status_code == 403


def test_operator_cannot_list_all_users(client, login):
    response = client.get("/users", headers=login("ops1@example.com"))
    assert response.status_code == 403


def test_admin_can_list_users(client, login):
    response = client.get("/users", headers=login("admin@example.com"))
    assert response.status_code == 200
    assert len(response.json()) >= 5


def test_admin_can_create_user(client, login):
    response = client.post(
        "/users",
        headers=login("admin@example.com"),
        json={
            "email": "new-op@example.com",
            "name": "New Op",
            "role": "operator",
            "password": "sup3rsecret",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "operator"

    # and the new user can actually log in
    login_response = client.post(
        "/auth/login", json={"email": "new-op@example.com", "password": "sup3rsecret"}
    )
    assert login_response.status_code == 200


def test_client_cannot_create_request_for_someone_else(client, login):
    # creation always binds the request to the caller; there is no client_id input
    response = client.post(
        "/requests",
        headers=login("client-a@example.com"),
        json={
            "task_name": "pick cup",
            "episodes_requested": 5,
            "deadline": "2026-12-01",
        },
    )
    assert response.status_code == 201
    assert response.json()["client_id"] != 0


def test_admin_can_do_operator_actions(client, login):
    # admin may import CSVs (operator action)
    response = client.get("/episodes", headers=login("admin@example.com"))
    assert response.status_code == 200


def test_client_cannot_transition_requests(client, users, login):
    create = client.post(
        "/requests",
        headers=login("client-a@example.com"),
        json={"task_name": "pick cup", "episodes_requested": 5, "deadline": "2026-12-01"},
    )
    request_id = create.json()["id"]
    response = client.post(
        f"/requests/{request_id}/transition",
        headers=login("client-a@example.com"),
        json={"to_status": "in_progress"},
    )
    assert response.status_code == 403
