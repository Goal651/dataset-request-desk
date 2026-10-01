"""Dataset requests: create, list, detail, and status transitions with audit trail."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.deps import CurrentUser, DbSession, require_role
from app.domain import DomainError, assert_transition
from app.models import (
    Assignment,
    DatasetRequest,
    RequestStatus,
    Role,
    StatusEvent,
    User,
)
from app.schemas import EpisodeSummaryOut, RequestDetailOut, RequestOut, StatusEventOut

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestCreateIn(BaseModel):
    task_name: str = Field(min_length=1, max_length=255)
    episodes_requested: int = Field(ge=1, le=100_000)
    deadline: date
    notes: str | None = Field(default=None, max_length=5000)


class TransitionIn(BaseModel):
    to_status: RequestStatus
    note: str | None = Field(default=None, max_length=2000)


def _load_request(request_id: int, db) -> DatasetRequest:
    req = db.get(DatasetRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return req


def _visible_to(user: User, req: DatasetRequest) -> None:
    # Clients may only see their own requests; anything else is 404 (no existence leak).
    if user.role == Role.client and req.client_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")


def count_active_assignments(db, request_id: int) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Assignment)
            .where(Assignment.request_id == request_id, Assignment.unassigned_at.is_(None))
        ).scalar_one()
    )


def _assigned_counts(db) -> dict[int, int]:
    rows = db.execute(
        select(Assignment.request_id, func.count())
        .where(Assignment.unassigned_at.is_(None))
        .group_by(Assignment.request_id)
    ).all()
    return {request_id: count for request_id, count in rows}


def _to_out(req: DatasetRequest, assigned_count: int) -> RequestOut:
    return RequestOut(
        id=req.id,
        task_name=req.task_name,
        episodes_requested=req.episodes_requested,
        deadline=req.deadline,
        notes=req.notes,
        status=req.status,
        client_id=req.client_id,
        client_name=req.client.name,
        assigned_count=assigned_count,
        created_at=req.created_at,
    )


def _to_detail_out(req: DatasetRequest, actor_names: dict[int, str]) -> RequestDetailOut:
    assigned = sorted(
        (a for a in req.assignments if a.unassigned_at is None), key=lambda a: a.id
    )
    return RequestDetailOut(
        id=req.id,
        task_name=req.task_name,
        episodes_requested=req.episodes_requested,
        deadline=req.deadline,
        notes=req.notes,
        status=req.status,
        client_id=req.client_id,
        client_name=req.client.name,
        assigned_count=len(assigned),
        created_at=req.created_at,
        episodes=[
            EpisodeSummaryOut(
                id=a.episode.id,
                episode_id=a.episode.episode_id,
                task_name=a.episode.task_name,
                quality=a.episode.quality,
                robot_id=a.episode.robot_id,
                export_status=latest_export_status(a),
            )
            for a in assigned
        ],
        events=[
            StatusEventOut(
                id=e.id,
                from_status=e.from_status,
                to_status=e.to_status,
                actor_id=e.actor_id,
                actor_name=actor_names.get(e.actor_id, f"user {e.actor_id}"),
                note=e.note,
                created_at=e.created_at,
            )
            for e in req.status_events
        ],
    )


def latest_export_status(assignment: Assignment) -> str | None:
    jobs = sorted(assignment.export_jobs, key=lambda j: j.id)
    return jobs[-1].status if jobs else None


@router.get("", response_model=list[RequestOut])
def list_requests(
    user: CurrentUser,
    db: DbSession,
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[RequestOut]:
    stmt = select(DatasetRequest).options(joinedload(DatasetRequest.client))
    if user.role == Role.client:
        stmt = stmt.where(DatasetRequest.client_id == user.id)
    if status_filter is not None:
        stmt = stmt.where(DatasetRequest.status == status_filter)
    stmt = stmt.order_by(DatasetRequest.id.desc()).limit(limit).offset(offset)
    counts = _assigned_counts(db)
    return [_to_out(r, counts.get(r.id, 0)) for r in db.scalars(stmt)]


@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreateIn,
    user: Annotated[User, Depends(require_role(Role.client))],
    db: DbSession,
) -> RequestOut:
    if payload.deadline <= date.today():
        raise DomainError("Deadline must be in the future")
    req = DatasetRequest(
        client_id=user.id,
        task_name=payload.task_name,
        episodes_requested=payload.episodes_requested,
        deadline=payload.deadline,
        notes=payload.notes,
        status=RequestStatus.submitted,
    )
    db.add(req)
    db.flush()
    db.add(
        StatusEvent(
            request_id=req.id,
            from_status=None,
            to_status=RequestStatus.submitted,
            actor_id=user.id,
            note="Request created",
        )
    )
    return _to_out(req, 0)


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(request_id: int, user: CurrentUser, db: DbSession) -> RequestDetailOut:
    req = _load_request(request_id, db)
    _visible_to(user, req)
    return _to_detail_out(req, _actor_names(db))


def _actor_names(db) -> dict[int, str]:
    return {u.id: u.name for u in db.scalars(select(User))}


@router.post("/{request_id}/transition", response_model=RequestOut)
def transition_request(
    request_id: int,
    payload: TransitionIn,
    user: CurrentUser,
    db: DbSession,
) -> RequestOut:
    req = _load_request(request_id, db)
    _visible_to(user, req)

    if payload.to_status == RequestStatus.delivered:
        assigned = count_active_assignments(db, req.id)
        if assigned < req.episodes_requested:
            raise DomainError(
                f"Cannot deliver: {assigned} of {req.episodes_requested} episodes assigned"
            )
    assert_transition(req.status, payload.to_status, user.role)

    from_status = req.status
    req.status = payload.to_status
    db.add(
        StatusEvent(
            request_id=req.id,
            from_status=from_status,
            to_status=payload.to_status,
            actor_id=user.id,
            note=payload.note,
        )
    )
    db.flush()
    return _to_out(req, count_active_assignments(db, req.id))
