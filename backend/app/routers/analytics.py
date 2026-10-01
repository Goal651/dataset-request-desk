"""Analytics: aggregations done in the database, not in Python."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.deps import DbSession, require_role
from app.domain import DomainError
from app.models import (
    DatasetRequest,
    Episode,
    EpisodeQuality,
    RequestStatus,
    Role,
    StatusEvent,
    User,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


class DailyRobotCount(BaseModel):
    day: date
    robot_id: str
    episodes_recorded: int


class Fulfilment(BaseModel):
    status_counts: dict[str, int]
    median_submitted_to_delivered_hours: float | None


class TopTask(BaseModel):
    task_name: str
    good_episodes: int


class AnalyticsOut(BaseModel):
    from_date: date
    to_date: date
    episodes_per_day_per_robot: list[DailyRobotCount]
    fulfilment: Fulfilment
    top_tasks: list[TopTask]


@router.get("", response_model=AnalyticsOut)
def analytics(
    _user: Annotated[User, Depends(require_role(Role.operator))],
    db: DbSession,
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
) -> AnalyticsOut:
    if from_date > to_date:
        raise DomainError("'from' must be on or before 'to'")

    # 1) Episodes recorded per day per robot. Indexed on recorded_at; grouped in SQL.
    day_start = func.date_trunc("day", Episode.recorded_at)
    per_day = db.execute(
        select(
            day_start.label("day"),
            Episode.robot_id,
            func.count().label("n"),
        )
        .where(
            Episode.recorded_at >= from_date,
            Episode.recorded_at < to_date + timedelta(days=1),
        )
        .group_by(day_start, Episode.robot_id)
        .order_by(day_start, Episode.robot_id)
    ).all()

    # 2) Request counts by status
    status_rows = db.execute(
        select(DatasetRequest.status, func.count()).group_by(DatasetRequest.status)
    ).all()

    # 3) Median submitted → delivered. Pairs each request's first 'delivered' event with
    #    its first 'submitted' event, then PERCENTILE_CONT(0.5) — the median is computed
    #    inside Postgres, never in Python.
    delivered_event = aliased(StatusEvent)
    submitted_event = aliased(StatusEvent)
    durations = (
        select(
            delivered_event.request_id,
            func.min(delivered_event.created_at - submitted_event.created_at).label("dur"),
        )
        .join(
            submitted_event,
            (submitted_event.request_id == delivered_event.request_id)
            & (submitted_event.to_status == RequestStatus.submitted),
        )
        .where(delivered_event.to_status == RequestStatus.delivered)
        .group_by(delivered_event.request_id)
        .subquery()
    )
    median_interval = db.execute(
        select(func.percentile_cont(0.5).within_group(durations.c.dur))
    ).scalar()

    median_hours: float | None = None
    if median_interval is not None:
        median_hours = round(median_interval.total_seconds() / 3600, 2)

    # 4) Top 5 tasks by good episodes
    top_tasks = db.execute(
        select(Episode.task_name, func.count())
        .where(
            Episode.quality == EpisodeQuality.good,
            Episode.recorded_at >= from_date,
            Episode.recorded_at < to_date + timedelta(days=1),
        )
        .group_by(Episode.task_name)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    return AnalyticsOut(
        from_date=from_date,
        to_date=to_date,
        episodes_per_day_per_robot=[
            DailyRobotCount(day=r.day.date(), robot_id=r.robot_id, episodes_recorded=r.n)
            for r in per_day
        ],
        fulfilment=Fulfilment(
            status_counts={s.value: c for s, c in status_rows},
            median_submitted_to_delivered_hours=median_hours,
        ),
        top_tasks=[TopTask(task_name=t, good_episodes=c) for t, c in top_tasks],
    )
