"""Submission creation, visibility, presentation, and rejudge rules."""

import asyncio
from datetime import datetime, timedelta, timezone

from backend.app.core.config import Settings
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.models import TestcaseStatus
from backend.app.modules.problems.service import ProblemService
from backend.app.modules.submissions.models import Submission, SubmissionRequest, SubmissionStatus
from backend.app.modules.submissions.repository import SubmissionRepository
from backend.app.modules.submissions.task_manager import EvaluationTaskManager
from backend.app.modules.users.models import User, UserRole


class SubmissionNotFoundError(Exception):
    pass


class SubmissionPermissionError(Exception):
    pass


class SubmissionRateLimitError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SubmissionService:
    def __init__(
        self,
        repository: SubmissionRepository,
        problem_service: ProblemService,
        language_service: LanguageService,
        task_manager: EvaluationTaskManager,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.problem_service = problem_service
        self.language_service = language_service
        self.task_manager = task_manager
        self.settings = settings
        self._creation_lock = asyncio.Lock()

    async def create(self, user: User, request: SubmissionRequest) -> Submission:
        async with self._creation_lock, self.problem_service.mutation_lock:
            return await self._create(user, request)

    async def _create(self, user: User, request: SubmissionRequest) -> Submission:
        from backend.app.modules.problems.repository import validate_problem_id

        validate_problem_id(request.problem_id)
        if len(request.code.encode("utf-8")) > self.settings.submission_code_limit:
            raise ValueError("code is too long")
        now = _utc_now()
        recent = await self.repository.count_recent(user.id, now - timedelta(minutes=1))
        if recent >= self.settings.submission_rate_limit_per_minute:
            raise SubmissionRateLimitError
        problem = await self.problem_service.get_problem(request.problem_id)
        await self.language_service.get_enabled(request.language)
        submission = await self.repository.create(
            user_id=user.id,
            problem_id=problem.id,
            language=request.language,
            code=request.code,
            counts=len(problem.testcases) * 10,
            now=now,
        )
        try:
            await self.task_manager.enqueue(
                submission.submission_id, submission.evaluation_version
            )
        except Exception:
            await self.repository.fail_if_current(
                submission.submission_id,
                submission.evaluation_version,
                "evaluation task could not be queued",
                _utc_now(),
            )
            raise
        return submission

    async def get_visible(self, user: User, submission_id: int) -> Submission:
        submission = await self.repository.get(submission_id)
        if submission is None:
            raise SubmissionNotFoundError
        if user.role is not UserRole.ADMIN and submission.user_id != user.id:
            raise SubmissionPermissionError
        return submission

    async def list_visible(
        self,
        user: User,
        *,
        user_id: int | None,
        problem_id: str | None,
        status: SubmissionStatus | None,
        page: int | None,
        page_size: int | None,
    ) -> tuple[int, list[Submission]]:
        if user.role is not UserRole.ADMIN and user_id is not None and user_id != user.id:
            raise SubmissionPermissionError
        if user_id is None and problem_id is None:
            raise ValueError("user_id or problem_id is required")
        if page is not None and page_size is None:
            raise ValueError("page_size is required when page is provided")
        if user.role is not UserRole.ADMIN:
            user_id = user.id
        return await self.repository.list_filtered(
            user_id=user_id,
            problem_id=problem_id,
            status=status,
            page=page,
            page_size=page_size,
        )

    async def rejudge(self, submission_id: int) -> Submission:
        submission = await self.repository.begin_rejudge(submission_id, _utc_now())
        if submission is None:
            raise SubmissionNotFoundError
        try:
            await self.task_manager.enqueue(
                submission.submission_id, submission.evaluation_version
            )
        except Exception:
            await self.repository.fail_if_current(
                submission.submission_id,
                submission.evaluation_version,
                "evaluation task could not be queued",
                _utc_now(),
            )
            raise
        return submission


def submission_summary(submission: Submission) -> dict[str, object]:
    data: dict[str, object] = {
        "submission_id": str(submission.submission_id),
        "status": submission.status.value,
    }
    if submission.status is SubmissionStatus.SUCCESS:
        data.update(score=submission.score, counts=submission.counts)
    return data


def submission_detail(submission: Submission) -> dict[str, object]:
    data: dict[str, object] = {
        "submission_id": str(submission.submission_id),
        "status": submission.status.value,
        "language": submission.language,
        "code": submission.code,
        "result": submission.result.value if submission.result is not None else None,
    }
    if submission.status is SubmissionStatus.PENDING:
        return data
    if submission.status is SubmissionStatus.ERROR:
        data.update(
            score=None,
            counts=submission.counts,
            compile_info=None,
            run_info=None,
            error_info=submission.stderr or "evaluation task failed",
        )
        return data
    compile_info: dict[str, str] | None
    if submission.compile_info is None:
        compile_info = None
    elif submission.result is TestcaseStatus.CE:
        compile_info = {"result": "error", "message": submission.compile_info}
    else:
        compile_info = {
            "result": "success",
            "message": "" if submission.compile_info == "success" else submission.compile_info,
        }
    if submission.result is TestcaseStatus.CE:
        run_info = {"result": "not started", "message": "compilation failed"}
    else:
        run_info = {
            "result": "finished",
            "message": f"{submission.counts // 10} test cases finished",
        }
    data.update(
        score=submission.score,
        counts=submission.counts,
        compile_info=compile_info,
        run_info=run_info,
        error_info="",
    )
    return data
