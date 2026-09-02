"""Evaluation-log visibility rules and structured access auditing."""

from datetime import datetime, timezone

from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.logs.models import EvaluationLogEntry
from backend.app.modules.logs.repository import EvaluationLogRepository
from backend.app.modules.problems.service import ProblemService
from backend.app.modules.submissions.models import Submission, SubmissionStatus
from backend.app.modules.submissions.repository import SubmissionRepository
from backend.app.modules.users.models import User, UserRole


class EvaluationLogNotFoundError(Exception):
    pass


class EvaluationLogPermissionError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationLogService:
    def __init__(
        self,
        repository: EvaluationLogRepository,
        submissions: SubmissionRepository,
        problems: ProblemService,
        audit: AuditService,
    ) -> None:
        self.repository = repository
        self.submissions = submissions
        self.problems = problems
        self.audit = audit

    async def get_visible(
        self, user: User, submission_id: int
    ) -> tuple[Submission, list[EvaluationLogEntry]]:
        submission = await self.submissions.get(submission_id)
        if submission is None:
            raise EvaluationLogNotFoundError
        permitted = (
            user.role is UserRole.ADMIN
            or submission.user_id == user.id
            or await self.repository.is_public(submission.problem_id)
        )
        await self.audit.record(
            actor_user_id=user.id,
            action="view_logs",
            target_type="submission",
            target_id=submission_id,
            success=permitted,
            status=200 if permitted else 403,
        )
        if not permitted:
            raise EvaluationLogPermissionError
        details = await self.repository.list_current(submission_id)
        return submission, details

    async def set_visibility(
        self, actor: User, problem_id: str, public_cases: bool
    ) -> bool:
        await self.problems.get_problem(problem_id)
        previous = await self.repository.set_public(problem_id, public_cases, _utc_now())
        await self.audit.record(
            actor_user_id=actor.id,
            action="update_log_visibility",
            target_type="problem",
            target_id=problem_id,
            success=True,
            status=200,
            changes={"before": previous, "after": public_cases},
        )
        return previous


def evaluation_log_data(
    submission: Submission, entries: list[EvaluationLogEntry]
) -> dict[str, object]:
    details = [
        {
            "id": entry.testcase_id,
            "result": entry.result,
            "time": entry.time,
            "memory": entry.memory,
            **({"error_summary": entry.error_summary} if entry.error_summary else {}),
        }
        for entry in entries
    ]
    return {
        "details": details,
        "score": submission.score if submission.status is SubmissionStatus.SUCCESS else None,
        "counts": submission.counts,
    }
