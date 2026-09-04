"""Structured security-audit data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuditLog:
    id: int
    actor_user_id: int | None
    action: str
    target_type: str
    target_id: str
    success: bool
    status: int
    changes: dict[str, object]
    created_at: datetime
    problem_id: str | None = None
    actor_username: str | None = None
