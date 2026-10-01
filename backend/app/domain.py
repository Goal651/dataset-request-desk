"""Pure domain rules: status machine, role permissions, assignment rules.

Kept free of FastAPI/SQLAlchemy so they are trivially unit-testable and can be
defended line by line in review.
"""

from __future__ import annotations

from app.models import EpisodeQuality, RequestStatus, Role

EXPORTABLE_QUALITIES = (EpisodeQuality.good, EpisodeQuality.usable)


class DomainError(Exception):
    """Raised when an operation violates a business rule; maps to HTTP 409/403."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# submitted → in_progress → delivered → accepted
#                                     ↘ rejected → in_progress (rework)
TRANSITIONS: dict[RequestStatus, dict[RequestStatus, set[Role]]] = {
    RequestStatus.submitted: {
        RequestStatus.in_progress: {Role.operator, Role.admin},
        RequestStatus.rejected: {Role.client},  # a client may reject a request immediately
    },
    RequestStatus.in_progress: {
        RequestStatus.delivered: {Role.operator, Role.admin},
    },
    RequestStatus.delivered: {
        RequestStatus.accepted: {Role.client},
        RequestStatus.rejected: {Role.client},
    },
    RequestStatus.rejected: {
        RequestStatus.in_progress: {Role.operator, Role.admin},  # rework
    },
    RequestStatus.accepted: {},  # terminal
}


def can_transition(current: RequestStatus, target: RequestStatus, role: Role) -> bool:
    return role in TRANSITIONS.get(current, {}).get(target, set())


def assert_transition(current: RequestStatus, target: RequestStatus, role: Role) -> None:
    if current == target:
        raise DomainError(f"Request is already {current.value}")
    if not can_transition(current, target, role):
        raise DomainError(
            f"Cannot move a request from {current.value} to {target.value} as {role.value}",
            status_code=403 if role == Role.client else 409,
        )


def assert_episode_assignable(quality: EpisodeQuality, already_assigned: bool) -> None:
    if already_assigned:
        raise DomainError("Episode is already assigned to a request")
    if quality not in EXPORTABLE_QUALITIES:
        raise DomainError(f"Episodes with quality '{quality.value}' cannot be assigned")
