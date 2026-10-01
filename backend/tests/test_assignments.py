"""Assignment rule tests: quality gate, one-request-at-a-time, status gating."""

from __future__ import annotations

import pytest

from sqlalchemy import select

from app.models import Episode


@pytest.fixture()
def prepared_request(client, login, db_session):
    """A request (in_progress) plus two good episodes and one bad one."""
    response = client.post(
        "/requests",
        headers=login("client-a@example.com"),
        json={"task_name": "pick cup", "episodes_requested": 2, "deadline": "2026-12-01"},
    )
    request_id = response.json()["id"]
    client.post(
        f"/requests/{request_id}/transition", headers=login("ops1@example.com"),
        json={"to_status": "in_progress"},
    )

    csv_content = (
        b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
        b"EP-70001,arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"
        b"EP-70002,arm-01,pick cup,2026-08-01T11:00:00,60,Aline,usable\n"
        b"EP-70003,arm-01,pick cup,2026-08-01T12:00:00,60,Aline,bad\n"
    )
    from app.routers.episodes import import_csv_bytes

    import_csv_bytes(csv_content, db_session)
    db_session.flush()

    episodes = {
        e.episode_id: e
        for e in db_session.scalars(
            select(Episode).where(Episode.episode_id.in_(["EP-70001", "EP-70002", "EP-70003"]))
        )
    }
    return request_id, episodes


def _assign(client, headers, request_id, episode_pk):
    return client.post(
        f"/requests/{request_id}/assignments", headers=headers, json={"episode_pk": episode_pk}
    )


def test_good_episode_assignable(client, login, prepared_request):
    request_id, episodes = prepared_request
    response = _assign(
        client, login("ops1@example.com"), request_id, episodes["EP-70001"].id
    )
    assert response.status_code == 201, response.text


def test_bad_episode_not_assignable(client, login, prepared_request):
    request_id, episodes = prepared_request
    response = _assign(
        client, login("ops1@example.com"), request_id, episodes["EP-70003"].id
    )
    assert response.status_code == 409
    assert "cannot be assigned" in response.json()["detail"]


def test_episode_only_one_request_at_a_time(client, login, prepared_request):
    request_id, episodes = prepared_request
    ops = login("ops1@example.com")

    other = client.post(
        "/requests",
        headers=login("client-b@example.com"),
        json={"task_name": "fold towel", "episodes_requested": 1, "deadline": "2026-12-01"},
    ).json()["id"]
    client.post(
        f"/requests/{other}/transition", headers=login("ops2@example.com"),
        json={"to_status": "in_progress"},
    )

    first = _assign(client, ops, request_id, episodes["EP-70001"].id)
    assert first.status_code == 201

    second = _assign(client, ops, other, episodes["EP-70001"].id)
    assert second.status_code == 409
    assert "already assigned" in second.json()["detail"]


def test_unassign_allows_reassignment(client, login, prepared_request):
    request_id, episodes = prepared_request
    ops = login("ops1@example.com")
    assignment = _assign(client, ops, request_id, episodes["EP-70001"].id).json()

    removed = client.delete(
        f"/requests/{request_id}/assignments/{assignment['id']}", headers=ops
    )
    assert removed.status_code == 204

    other = client.post(
        "/requests",
        headers=login("client-b@example.com"),
        json={"task_name": "fold towel", "episodes_requested": 1, "deadline": "2026-12-01"},
    ).json()["id"]
    client.post(
        f"/requests/{other}/transition", headers=login("ops2@example.com"),
        json={"to_status": "in_progress"},
    )
    reassign = _assign(client, ops, other, episodes["EP-70001"].id)
    assert reassign.status_code == 201


def test_cannot_assign_to_delivered_request(client, login, prepared_request):
    request_id, episodes = prepared_request
    ops = login("ops1@example.com")
    _assign(client, ops, request_id, episodes["EP-70001"].id)
    _assign(client, ops, request_id, episodes["EP-70002"].id)
    delivered = client.post(
        f"/requests/{request_id}/transition", headers=ops, json={"to_status": "delivered"}
    )
    assert delivered.status_code == 200

    csv_extra = (
        b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
        b"EP-70004,arm-01,pick cup,2026-08-01T13:00:00,60,Aline,good\n"
    )
    from app.routers.episodes import import_csv_bytes

    # import via the same session so the new episode is visible
    from app.deps import get_db  # noqa: F401

    response = client.post(
        "/episodes/import",
        files={"file": ("more.csv", __import__("io").BytesIO(csv_extra), "text/csv")},
        headers=ops,
    )
    assert response.status_code == 200

    listing = client.get(
        "/episodes", headers=ops, params={"task_name": "pick cup", "limit": 500}
    ).json()
    ep70004 = next(e for e in listing if e["episode_id"] == "EP-70004")

    late = _assign(client, ops, request_id, ep70004["id"])
    assert late.status_code == 409


def test_client_cannot_assign(client, login, prepared_request):
    request_id, episodes = prepared_request
    response = _assign(
        client, login("client-a@example.com"), request_id, episodes["EP-70001"].id
    )
    assert response.status_code == 403
