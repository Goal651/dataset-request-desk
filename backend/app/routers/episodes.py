"""Episodes: listing with filters, and the idempotent CSV import."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import String, select
from sqlalchemy.orm import Session

from app.deps import DbSession, require_role
from app.models import Assignment, Episode, EpisodeQuality, Role, User

router = APIRouter(prefix="/episodes", tags=["episodes"])

# From seed/README.md. A row with an unknown robot is suspicious data, not a new robot;
# we skip it and say why. The set is injected as env in production.
KNOWN_ROBOTS = {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"}

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",   # canonical: 2026-08-16T23:28:00
    "%Y-%m-%dT%H:%M:%SZ",  # trailing Z variant
    "%Y-%m-%d %H:%M:%S",   # space separator
    "%Y-%m-%d",            # date only
    "%d/%m/%Y %H:%M",      # EU style seen in the export
)
MAX_IMPORT_BYTES = 10 * 1024 * 1024


class ImportErrorReason(Exception):
    """Internal signal: why a row could not be imported."""


def parse_timestamp(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_quality(raw: str | None) -> EpisodeQuality | None:
    value = (raw or "").strip().lower()
    try:
        return EpisodeQuality(value)
    except ValueError:
        return None


def parse_duration(raw: str | None) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value >= 0 else None


@dataclass
class RowResult:
    row_number: int
    episode_id: str | None
    action: str  # imported | updated | skipped
    reason: str | None = None


@dataclass
class ImportReport:
    rows_seen: int = 0
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    rows: list[RowResult] = field(default_factory=list)


def import_csv_bytes(content: bytes, db: Session) -> ImportReport:
    """Import a messy CSV idempotently.

    - One query loads all existing episode_ids up front (no per-row lookups);
      rows already present are treated as upserts and reported as `updated`.
    - Validation happens per row; a bad row is skipped with a reason and never
      aborts the file.
    - Re-running the same file is safe: imported stays 0, nothing duplicates.
    """
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    now = datetime.now(timezone.utc)
    existing: dict[str, Episode] = {e.episode_id: e for e in db.scalars(select(Episode))}

    to_upsert: list[tuple[int, str, dict]] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw_row.values() if value is not None):
            continue  # blank line
        report.rows_seen += 1

        episode_id = (raw_row.get("episode_id") or "").strip().upper()
        try:
            if not episode_id:
                raise ImportErrorReason("missing episode_id")
            if not (raw_row.get("robot_id") or "").strip():
                raise ImportErrorReason("missing robot_id")
            robot_id = raw_row["robot_id"].strip().lower()
            if robot_id not in KNOWN_ROBOTS:
                raise ImportErrorReason(f"unknown robot_id '{robot_id}'")

            recorded_at = parse_timestamp(raw_row.get("recorded_at") or "")
            if recorded_at is None:
                raise ImportErrorReason(
                    f"unparseable recorded_at '{(raw_row.get('recorded_at') or '').strip()}'"
                )
            if recorded_at > now + timedelta(days=1):
                raise ImportErrorReason(f"recorded_at is in the future ({recorded_at.date()})")

            duration = parse_duration(raw_row.get("duration_seconds"))
            if duration is None:
                raise ImportErrorReason(
                    f"invalid duration_seconds '{(raw_row.get('duration_seconds') or '').strip()}'"
                )

            quality = parse_quality(raw_row.get("quality"))
            if quality is None:
                raise ImportErrorReason(
                    f"invalid quality '{(raw_row.get('quality') or '').strip()}'"
                )

            task_name = (raw_row.get("task_name") or "").strip().lower()
            if not task_name:
                raise ImportErrorReason("missing task_name")

            operator_name = (raw_row.get("operator_name") or "").strip()
            if not operator_name:
                raise ImportErrorReason("missing operator_name")
        except ImportErrorReason as exc:
            report.skipped += 1
            report.rows.append(RowResult(row_number, episode_id or None, "skipped", str(exc)))
            continue

        to_upsert.append(
            (
                row_number,
                episode_id,
                {
                    "robot_id": robot_id,
                    "task_name": task_name,
                    "recorded_at": recorded_at,
                    "duration_seconds": duration,
                    "operator_name": operator_name,
                    "quality": quality,
                },
            )
        )

    for row_number, episode_id, values in to_upsert:
        current = existing.get(episode_id)
        if current is None:
            current = Episode(episode_id=episode_id, **values)
            db.add(current)
            existing[episode_id] = current  # duplicate rows within one file are deduped too
            report.imported += 1
            report.rows.append(RowResult(row_number, episode_id, "imported"))
        else:
            for key, value in values.items():
                setattr(current, key, value)
            report.updated += 1
            report.rows.append(RowResult(row_number, episode_id, "updated", "already present"))

    return report


class EpisodeOut(BaseModel):
    id: int
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: float
    operator_name: str
    quality: EpisodeQuality
    assigned_request_id: int | None = None

    model_config = {"from_attributes": True}


class ImportReportOut(BaseModel):
    rows_seen: int
    imported: int
    updated: int
    skipped: int
    rows: list[RowResult]


@router.get("", response_model=list[EpisodeOut])
def list_episodes(
    _user: Annotated[User, Depends(require_role(Role.client, Role.operator))],
    db: DbSession,
    task_name: str | None = Query(default=None, description="Case-insensitive substring"),
    quality: EpisodeQuality | None = None,
    robot_id: str | None = None,
    unassigned_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[EpisodeOut]:
    active = select(Assignment.episode_id).where(Assignment.unassigned_at.is_(None))
    stmt = select(Episode)
    if task_name:
        stmt = stmt.where(Episode.task_name.ilike(f"%{task_name}%"))
    if quality is not None:
        stmt = stmt.where(Episode.quality == quality)
    if robot_id:
        stmt = stmt.where(Episode.robot_id == robot_id)
    if unassigned_only:
        stmt = stmt.where(Episode.id.not_in(active))
    stmt = stmt.order_by(Episode.episode_id.cast(String)).limit(limit).offset(offset)

    assigned_now = {
        row[0]: row[1]
        for row in db.execute(
            select(Assignment.episode_id, Assignment.request_id).where(
                Assignment.unassigned_at.is_(None)
            )
        )
    }
    result = []
    for episode in db.scalars(stmt):
        out = EpisodeOut.model_validate(episode)
        out.assigned_request_id = assigned_now.get(episode.id)
        result.append(out)
    return result


@router.post("/import", response_model=ImportReportOut)
def import_episodes(
    file: Annotated[UploadFile, File()],
    _operator: Annotated[User, Depends(require_role(Role.operator))],
    db: DbSession,
) -> ImportReportOut:
    content = file.file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    report = import_csv_bytes(content, db)
    return ImportReportOut(
        rows_seen=report.rows_seen,
        imported=report.imported,
        updated=report.updated,
        skipped=report.skipped,
        rows=report.rows,
    )
