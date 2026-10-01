"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("organisation", sa.String(255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("client", "operator", "admin", name="user_role", native_enum=True),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.String(64), nullable=False, unique=True),
        sa.Column("robot_id", sa.String(64), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Numeric(10, 1), nullable=False),
        sa.Column("operator_name", sa.String(255), nullable=False),
        sa.Column(
            "quality",
            sa.Enum("good", "usable", "bad", name="episode_quality", native_enum=True),
            nullable=False,
        ),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_seconds >= 0", name="ck_episode_duration_nonneg"),
    )
    op.create_index("ix_episodes_task_name", "episodes", ["task_name"])
    op.create_index("ix_episodes_recorded_at", "episodes", ["recorded_at"])
    op.create_index("ix_episodes_quality", "episodes", ["quality"])
    op.create_table(
        "requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("episodes_requested", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "submitted",
                "in_progress",
                "delivered",
                "accepted",
                "rejected",
                name="request_status",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("episodes_requested > 0", name="ck_request_count_pos"),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "episode_id", "unassigned_at", name="uq_assignment_active_episode",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "status_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "submitted", "in_progress", "delivered", "accepted", "rejected",
                name="request_status", native_enum=True, create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "submitted", "in_progress", "delivered", "accepted", "rejected",
                name="request_status", native_enum=True, create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending','running','done','failed')", name="ck_export_job_status"
        ),
    )


def downgrade() -> None:
    op.drop_table("export_jobs")
    op.drop_table("status_events")
    op.drop_table("assignments")
    op.drop_table("requests")
    op.drop_index("ix_episodes_quality", table_name="episodes")
    op.drop_index("ix_episodes_recorded_at", table_name="episodes")
    op.drop_index("ix_episodes_task_name", table_name="episodes")
    op.drop_table("episodes")
    op.drop_table("users")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="episode_quality").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="request_status").drop(op.get_bind(), checkfirst=True)
