"""Assignments: operators assign episodes to requests, with domain-rule enforcement."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DbSession, require_role
from app.domain import DomainError, assert_episode_assignable
from app.models import (
    Assignment,
    DatasetRequest,
    Episode,
    ExportJob,
    RequestStatus,
    Role,
    User,
    utcnow,
)

router = APIRouter(prefix="/requests/{request_id}/assignments", tags=["assignments"])


class AssignmentIn(BaseModel):
    episode_pk: int = Field(description="Episode database id")


class AssignmentOut(BaseModel):
    id: int
    request_id: int
    episode_id: int
    episode_ref: str
    export_status: str | None = None


def _load_request(request_id: int, db) -> DatasetRequest:
    req = db.get(DatasetRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return req


def _load_episode(episode_pk: int, db) -> Episode:
    episode = db.get(Episode, episode_pk)
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Episode not found")
    return episode


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def assign(
    request_id: int,
    payload: AssignmentIn,
    _operator: Annotated[User, Depends(require_role(Role.operator))],
    db: DbSession,
) -> AssignmentOut:
    req = _load_request(request_id, db)
    episode = _load_episode(payload.episode_pk, db)

    already = db.execute(
        select(Assignment).where(
            Assignment.episode_id == episode.id, Assignment.unassigned_at.is_(None)
        )
    ).scalar_one_or_none()
    assert_episode_assignable(episode.quality, already is not None)

    # Deliverable request statuses: only these accept new assignments.
    deliverable = {RequestStatus.submitted, RequestStatus.in_progress, RequestStatus.rejected}
    if req.status not in deliverable:
        raise DomainError(f"Cannot assign episodes to a {req.status.value} request")

    assignment = Assignment(request_id=req.id, episode_id=episode.id, assigned_by=_operator.id)
    db.add(assignment)
    db.flush()
    db.add(ExportJob(assignment_id=assignment.id, status="pending"))
    return AssignmentOut(
        id=assignment.id,
        request_id=req.id,
        episode_id=episode.id,
        episode_ref=episode.episode_id,
        export_status="pending",
    )


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign(
    request_id: int,
    assignment_id: int,
    _operator: Annotated[User, Depends(require_role(Role.operator))],
    db: DbSession,
) -> None:
    assignment = db.get(Assignment, assignment_id)
    if (
        assignment is None
        or assignment.request_id != request_id
        or assignment.unassigned_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    assignment.unassigned_at = utcnow()
    # Keep export jobs; the trail remains for audit.
