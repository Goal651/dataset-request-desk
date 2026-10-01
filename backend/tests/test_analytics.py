"""Analytics tests: DB-side aggregations return correct numbers."""

from __future__ import annotations

from datetime import date, datetime

from app.models import DatasetRequest, RequestStatus, StatusEvent, User
from app.routers.episodes import import_csv_bytes

CSV = (
    b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
    b"EP-80001,arm-01,pick cup,2026-08-10T10:00:00,60,Aline,good\n"
    b"EP-80002,arm-01,pick cup,2026-08-10T11:00:00,60,Aline,good\n"
    b"EP-80003,arm-02,pick cup,2026-08-10T12:00:00,60,Eric,usable\n"
    b"EP-80004,arm-02,open drawer,2026-08-11T10:00:00,60,Eric,good\n"
    b"EP-80005,arm-03,pick cup,2026-08-12T10:00:00,60,Diane,bad\n"
)


def _seed_episodes(db_session):
    report = import_csv_bytes(CSV, db_session)
    db_session.flush()
    assert report.imported == 5


def _user_id(db_session, email: str) -> int:
    return db_session.query(User).filter(User.email == email).one().id


def _analytics(client, login, **params):
    return client.get(
        "/analytics",
        headers=login("ops1@example.com"),
        params={"from": "2026-08-10", "to": "2026-08-12", **params},
    )


def test_analytics_counts(client, login, db_session):
    _seed_episodes(db_session)
    response = _analytics(client, login)
    assert response.status_code == 200, response.text
    body = response.json()

    per_day = {
        (d["day"], d["robot_id"]): d["episodes_recorded"]
        for d in body["episodes_per_day_per_robot"]
    }
    assert per_day[("2026-08-10", "arm-01")] == 2
    assert per_day[("2026-08-10", "arm-02")] == 1
    assert per_day[("2026-08-11", "arm-02")] == 1
    assert per_day[("2026-08-12", "arm-03")] == 1

    tasks = {t["task_name"]: t["good_episodes"] for t in body["top_tasks"]}
    assert tasks["pick cup"] == 2  # only the two good ones, not the bad EP-80005
    assert tasks["open drawer"] == 1


def test_analytics_requires_operator(client, login):
    response = client.get(
        "/analytics",
        headers=login("client-a@example.com"),
        params={"from": "2026-08-10", "to": "2026-08-12"},
    )
    assert response.status_code == 403


def test_analytics_rejects_inverted_range(client, login):
    response = client.get(
        "/analytics",
        headers=login("ops1@example.com"),
        params={"from": "2026-08-12", "to": "2026-08-10"},
    )
    assert response.status_code == 409


def test_median_submitted_to_delivered(client, login, db_session):
    """Requests delivered 2h and 4h after submission -> median 3h, computed in SQL."""
    client_a = _user_id(db_session, "client-a@example.com")
    ops1 = _user_id(db_session, "ops1@example.com")

    # request 1: submitted 08:00, delivered 10:00 (2h)
    # request 2: submitted 08:00, delivered 12:00 (4h)
    for delivered_at in (datetime(2026, 8, 1, 10, 0), datetime(2026, 8, 1, 12, 0)):
        req = DatasetRequest(
            client_id=client_a,
            task_name="pick cup",
            episodes_requested=1,
            deadline=date(2026, 12, 1),
            status=RequestStatus.delivered,
        )
        db_session.add(req)
        db_session.flush()
        db_session.add(
            StatusEvent(
                request_id=req.id,
                from_status=None,
                to_status=RequestStatus.submitted,
                actor_id=client_a,
                created_at=datetime(2026, 8, 1, 8, 0),
            )
        )
        db_session.add(
            StatusEvent(
                request_id=req.id,
                from_status=RequestStatus.in_progress,
                to_status=RequestStatus.delivered,
                actor_id=ops1,
                created_at=delivered_at,
            )
        )
    db_session.flush()

    body = client.get(
        "/analytics",
        headers=login("ops1@example.com"),
        params={"from": "2026-08-01", "to": "2026-08-02"},
    ).json()
    assert body["fulfilment"]["median_submitted_to_delivered_hours"] == 3.0
