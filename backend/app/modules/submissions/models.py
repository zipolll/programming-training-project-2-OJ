"""Submission persistence and API models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from backend.app.modules.judge.models import TestcaseStatus


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


class SubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    problem_id: str = Field(min_length=1, max_length=64)
    language: str = Field(min_length=1, max_length=32)
    code: str = Field(min_length=1, max_length=1_000_000)


@dataclass(frozen=True)
class Submission:
    submission_id: int
    user_id: int
    problem_id: str
    language: str
    code: str
    status: SubmissionStatus
    result: TestcaseStatus | None
    score: int | None
    counts: int
    compile_info: str | None
    stdout: str | None
    stderr: str | None
    time: float | None
    memory: float | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    evaluation_version: int
