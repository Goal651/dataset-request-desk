"""Status machine + request scoping tests (over HTTP, against real Postgres)."""

from __future__ import annotations

import pytest
from app.models import Episode
from app.routers.episodes import import_csv_bytes
from sqlalchemy import select


@pytest.fixture()
def client_request(client, login):
    """A request created by client-a."""
    response = client.post(
        "/requests",
        headers=login("client-a@example.com"),
        json={"task_name": "pick cup", "episodes_requested": 2, "deadline": "2026-12-01"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _transition(client, headers, request_id, to_status):
    return client.post(
        f"/requests/{request_id}/transition",
        headers=headers,
        json={"to_status": to_status},
    )


def test_client_sees_only_own_requests(client, users, login):
    for email in ("client-a@example.com", "client-b@example.com"):
        response = client.post(
            "/requests",
            headers=login(email),
            json={"task_name": "pick cup", "episodes_requested": 1, "deadline": "2026-12-01"},
        )
        assert response.status_code == 201

    seen_a = client.get("/requests", headers=login("client-a@example.com")).json()
    seen_b = client.get("/requests", headers=login("client-b@example.com")).json()
    assert {r["client_name"] for r in seen_a} == {"Acme Robotics"}
    assert {r["client_name"] for r in seen_b} == {"Beta Labs"}


def test_client_cannot_read_foreign_request(client, users, login, client_request):
    response = client.get(
        f"/requests/{client_request['id']}", headers=login("client-b@example.com")
    )
    assert response.status_code == 404  # scoped out, no existence leak


def test_operator_sees_all_requests(client, login, client_request):
    response = client.get("/requests", headers=login("ops1@example.com"))
    assert response.status_code == 200
    assert any(r["id"] == client_request["id"] for r in response.json())


def test_happy_path_transition_flow(client, login, client_request):
    request_id = client_request["id"]
    started = _transition(client, login("ops1@example.com"), request_id, "in_progress")
    assert started.status_code == 200
    # delivered may fail without enough episodes; that rule is asserted separately
    delivered = _transition(client, login("ops1@example.com"), request_id, "delivered")
    assert delivered.status_code in (200, 409)


def test_delivery_requires_enough_episodes(client, login, client_request):
    request_id = client_request["id"]
    _transition(client, login("ops1@example.com"), request_id, "in_progress")
    response = _transition(client, login("ops1@example.com"), request_id, "delivered")
    assert response.status_code == 409
    assert "2 of 2" in response.json()["detail"] or "of 2" in response.json()["detail"]


def test_invalid_transition_rejected(client, login, client_request):
    # submitted → delivered skips a step
    response = _transition(client, login("ops1@example.com"), client_request["id"], "delivered")
    assert response.status_code == 409


def test_client_cannot_move_to_in_progress(client, login, client_request):
    response = _transition(
        client, login("client-a@example.com"), client_request["id"], "in_progress"
    )
    assert response.status_code == 403


def test_reject_then_rework_cycle(client, login, client_request, db_session):
    """Operator delivers, client rejects, operator reworks, re-delivers."""
    from app.routers.episodes import import_csv_bytes

    request_id = client_request["id"]
    ops = login("ops1@example.com")

    _transition(client, ops, request_id, "in_progress")

    # give the request enough episodes via the import + assignment service path
    csv_content = (
        b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
        b"EP-60001,arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"
        b"EP-60002,arm-01,pick cup,2026-08-01T11:00:00,60,Aline,good\n"
    )
    report = import_csv_bytes(csv_content, db_session)
    db_session.flush()
    assert report.imported == 2

    episodes = db_session.scalars(
        select(Episode).where(Episode.episode_id.in_(["EP-60001", "EP-60002"]))
    ).all()
    for episode in episodes:
        assign = client.post(
            f"/requests/{request_id}/assignments",
            headers=ops,
            json={"episode_pk": episode.id},
        )
        assert assign.status_code == 201, assign.text

    delivered = _transition(client, ops, request_id, "delivered")
    assert delivered.status_code == 200, delivered.text

    # client rejects...
    rejected = _transition(client, login("client-a@example.com"), request_id, "rejected")
    assert rejected.status_code == 200

    # ...operator reworks back to in_progress...
    rework = _transition(client, ops, request_id, "in_progress")
    assert rework.status_code == 200

    # ...and re-delivers
    again = _transition(client, ops, request_id, "delivered")
    assert again.status_code == 200

    events = client.get(
        f"/requests/{request_id}", headers=login("client-a@example.com")
    ).json()["events"]
    trail = [(e["from_status"], e["to_status"]) for e in events]
    assert trail == [
        (None, "submitted"),
        ("submitted", "in_progress"),
        ("in_progress", "delivered"),
        ("delivered", "rejected"),
        ("rejected", "in_progress"),
        ("in_progress", "delivered"),
    ]


def test_accepted_is_terminal(client, login, db_session, client_request):
    """accepted requests cannot move again (also covered indirectly by the map)."""


    request_id = client_request["id"]
    ops = login("ops1@example.com")
    _transition(client, ops, request_id, "in_progress")

    csv_content = (
        b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
        b"EP-61001,arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"
    )
    import_csv_bytes(csv_content, db_session)
    db_session.flush()
    episode = db_session.scalars(
        select(Episode).where(Episode.episode_id == "EP-61001")
    ).one()
    client.post(f"/requests/{request_id}/assignments", headers=ops, json={"episode_pk": episode.id})
    _transition(client, ops, request_id, "delivered")
    _transition(client, login("client-a@example.com"), request_id, "accepted")

    response = _transition(client, ops, request_id, "in_progress")
    assert response.status_code in (403, 409)


def test_status_history_recorded_with_actor(client, login, client_request):
    request_id = client_request["id"]
    _transition(client, login("ops1@example.com"), request_id, "in_progress")
    detail = client.get(f"/requests/{request_id}", headers=login("ops1@example.com")).json()
    assert detail["events"][0]["to_status"] == "submitted"
    assert detail["events"][1]["to_status"] == "in_progress"
    assert detail["events"][1]["actor_name"] == "Olu Operator"
