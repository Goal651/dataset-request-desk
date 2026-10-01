"""Pydantic schemas for request endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.models import EpisodeQuality, RequestStatus


class EpisodeSummaryOut(BaseModel):
    id: int
    episode_id: str
    task_name: str
    quality: EpisodeQuality
    robot_id: str
    export_status: str | None = None

    model_config = {"from_attributes": True}


class StatusEventOut(BaseModel):
    id: int
    from_status: RequestStatus | None
    to_status: RequestStatus
    actor_id: int
    actor_name: str
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RequestOut(BaseModel):
    id: int
    task_name: str
    episodes_requested: int
    deadline: date
    notes: str | None
    status: RequestStatus
    client_id: int
    client_name: str
    assigned_count: int
    created_at: datetime


class RequestDetailOut(RequestOut):
    episodes: list[EpisodeSummaryOut]
    events: list[StatusEventOut]
