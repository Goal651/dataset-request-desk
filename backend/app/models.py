"""SQLAlchemy models — the data model is documented in NOTES.md."""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(str, enum.Enum):
    client = "client"
    operator = "operator"
    admin = "admin"


class EpisodeQuality(str, enum.Enum):
    good = "good"
    usable = "usable"
    bad = "bad"


class RequestStatus(str, enum.Enum):
    submitted = "submitted"
    in_progress = "in_progress"
    delivered = "delivered"
    accepted = "accepted"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organisation: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    robot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Numeric(10, 1), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quality: Mapped[EpisodeQuality] = mapped_column(
        Enum(EpisodeQuality, name="episode_quality"), nullable=False
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("duration_seconds >= 0", name="ck_episode_duration_nonneg"),
        Index("ix_episodes_task_name", "task_name"),
        Index("ix_episodes_recorded_at", "recorded_at"),
        Index("ix_episodes_quality", "quality"),
    )


class DatasetRequest(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    episodes_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status"), nullable=False, default=RequestStatus.submitted
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    client: Mapped[User] = relationship(lazy="joined")
    assignments: Mapped[list[Assignment]] = relationship(back_populates="request")
    status_events: Mapped[list[StatusEvent]] = relationship(
        back_populates="request", order_by="StatusEvent.created_at"
    )

    __table_args__ = (CheckConstraint("episodes_requested > 0", name="ck_request_count_pos"),)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[DatasetRequest] = relationship(back_populates="assignments")
    episode: Mapped[Episode] = relationship(lazy="joined")
    export_jobs: Mapped[list[ExportJob]] = relationship(order_by="ExportJob.id")

    __table_args__ = (
        # "At most one request at a time": only the active assignment is unique;
        # unassigned rows keep the audit trail (unassigned_at set).
        UniqueConstraint(
            "episode_id",
            "unassigned_at",
            name="uq_assignment_active_episode",
            postgresql_nulls_not_distinct=True,
        ),
    )


class StatusEvent(Base):
    """Audit trail: every request status change, who did it, when."""

    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    from_status: Mapped[RequestStatus | None] = mapped_column(
        Enum(RequestStatus, name="request_status")
    )
    to_status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus, name="request_status"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[DatasetRequest] = relationship(back_populates="status_events")


class ExportJob(Base):
    """Simulated export pipeline for an assignment (stretch: background work)."""

    __tablename__ = "export_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','done','failed')", name="ck_export_job_status"
        ),
    )
