"""Export job status (stretch: background work) — visibility + manual retry."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import CurrentUser, DbSession, require_role
from app.models import Assignment, DatasetRequest, ExportJob, Role

router = APIRouter(prefix="/requests/{request_id}/exports", tags=["exports"])


class ExportJobOut(BaseModel):
    id: int
    assignment_id: int
    episode_ref: str
    status: str
    attempt: int
    error: str | None
    updated_at: datetime


class RetryIn(BaseModel):
    pass


def _request_or_404(request_id: int, user: CurrentUser, db) -> DatasetRequest:
    req = db.get(DatasetRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if user.role.value == "client" and req.client_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return req


@router.get("", response_model=list[ExportJobOut])
def list_exports(request_id: int, user: CurrentUser, db: DbSession) -> list[ExportJobOut]:
    req = _request_or_404(request_id, user, db)
    out: list[ExportJobOut] = []
    for a in req.assignments:
        if a.unassigned_at is not None:
            continue
        job = a.export_jobs[-1] if a.export_jobs else None
        if job is None:
            continue
        out.append(
            ExportJobOut(
                id=job.id,
                assignment_id=a.id,
                episode_ref=a.episode.episode_id,
                status=job.status,
                attempt=job.attempt,
                error=job.error,
                updated_at=job.updated_at,
            )
        )
    return out


@router.post("/{job_id}/retry", response_model=ExportJobOut)
def retry_job(
    request_id: int,
    job_id: int,
    _operator: Annotated[object, Depends(require_role(Role.operator))],
    user: CurrentUser,
    db: DbSession,
) -> ExportJobOut:
    _request_or_404(request_id, user, db)
    job = db.get(ExportJob, job_id)
    assignment = db.get(Assignment, job.assignment_id) if job else None
    if job is None or assignment is None or assignment.request_id != request_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export job not found")
    if job.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed jobs can be retried")
    job.status = "pending"
    job.error = None
    db.flush()
    return ExportJobOut(
        id=job.id,
        assignment_id=job.assignment_id,
        episode_ref=assignment.episode.episode_id,
        status=job.status,
        attempt=job.attempt,
        error=job.error,
        updated_at=job.updated_at,
    )
