"""Persistent evaluation-log and audit-log data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EvaluationLogEntry:
    submission_id: int
    evaluation_version: int
    testcase_id: int
    result: str
    time: float
    memory: float
    error_summary: str
    completed_at: datetime | None
