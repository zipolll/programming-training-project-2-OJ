"""Evaluation-log access rules and structured access auditing."""

from dataclasses import replace

from backend.app.modules.judge.models import TestcaseStatus
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.logs.models import EvaluationLogEntry
from backend.app.modules.logs.repository import EvaluationLogRepository
from backend.app.modules.submissions.models import Submission, SubmissionStatus
from backend.app.modules.submissions.repository import SubmissionRepository
from backend.app.modules.users.models import User, UserRole


class EvaluationLogNotFoundError(Exception):
    pass


class EvaluationLogPermissionError(Exception):
    pass


class EvaluationLogService:
    def __init__(
        self,
        repository: EvaluationLogRepository,
        submissions: SubmissionRepository,
        audit: AuditService,
    ) -> None:
        self.repository = repository
        self.submissions = submissions
        self.audit = audit

    async def get_visible(
        self, user: User, submission_id: int
    ) -> tuple[Submission, list[EvaluationLogEntry] | None]:
        submission = await self.submissions.get(submission_id)
        if submission is None:
            raise EvaluationLogNotFoundError
        public = await self.repository.is_public(submission.problem_id)
        permitted = user.role is UserRole.ADMIN or submission.user_id == user.id or public
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
        details = (
            await self.repository.list_current(submission_id)
            if user.role is UserRole.ADMIN or public else None
        )
        if (details is not None and user.role is not UserRole.ADMIN
                and submission.user_id != user.id):
            details = [replace(entry, error_summary="") for entry in details]
        return submission, details

def evaluation_log_data(
    submission: Submission, entries: list[EvaluationLogEntry] | None
) -> dict[str, object]:
    details = [
        {
            "id": entry.testcase_id,
            "result": entry.result,
            "time": entry.time,
            "memory": entry.memory,
            **({"error_summary": entry.error_summary} if entry.error_summary else {}),
        }
        for entry in entries or []
    ]
    # Legacy CE submissions predate per-case records. Use the stored total,
    # never the (possibly edited or deleted) problem's current testcase list.
    if (entries is not None and not details and submission.status is SubmissionStatus.SUCCESS
            and submission.result is TestcaseStatus.CE):
        details = [
            {"id": index, "result": "CE", "time": 0.0, "memory": 0.0,
             "error_summary": "编译失败，未运行"}
            for index in range(1, submission.counts // 10 + 1)
        ]
    return {
        **({"details": details} if entries is not None else {}),
        "score": submission.score if submission.status is SubmissionStatus.SUCCESS else None,
        "counts": submission.counts,
    }
