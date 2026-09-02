"""Single-worker lifecycle manager for persistent submission evaluations."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone

from backend.app.core.config import Settings
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.models import JudgeRequest
from backend.app.modules.judge.service import JudgeService
from backend.app.modules.problems.service import ProblemService
from backend.app.modules.submissions.models import SubmissionStatus
from backend.app.modules.submissions.repository import SubmissionRepository

logger = logging.getLogger(__name__)
TaskKey = tuple[int, int]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


class EvaluationTaskManager:
    """Own every queued/running evaluation and serialize execution through one worker."""

    def __init__(
        self,
        repository: SubmissionRepository,
        problem_service: ProblemService,
        language_service: LanguageService,
        judge_service: Callable[[], JudgeService],
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.problem_service = problem_service
        self.language_service = language_service
        self._judge_service = judge_service
        self.settings = settings
        self._queue: asyncio.Queue[TaskKey] = asyncio.Queue()
        self._tracked: set[TaskKey] = set()
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False

    @property
    def tracked(self) -> frozenset[TaskKey]:
        return frozenset(self._tracked)

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._accepting = True
        self._worker = asyncio.create_task(self._run(), name="submission-evaluation-worker")
        for submission_id, version in await self.repository.list_pending():
            await self.enqueue(submission_id, version)

    async def enqueue(self, submission_id: int, evaluation_version: int) -> bool:
        if not self._accepting:
            raise RuntimeError("evaluation manager is not accepting work")
        key = (submission_id, evaluation_version)
        if key in self._tracked:
            return False
        self._tracked.add(key)
        try:
            self._queue.put_nowait(key)
        except BaseException:
            self._tracked.discard(key)
            raise
        return True

    async def stop(self) -> None:
        self._accepting = False
        worker = self._worker
        if worker is None:
            return
        try:
            await asyncio.wait_for(
                self._queue.join(),
                timeout=self.settings.evaluation_shutdown_timeout_seconds,
            )
        except asyncio.TimeoutError:
            worker.cancel()
        else:
            worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        self._worker = None
        self._tracked.clear()

    async def _run(self) -> None:
        while True:
            key = await self._queue.get()
            try:
                await self._evaluate(*key)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected failure escaped submission evaluation %s", key[0])
            finally:
                self._tracked.discard(key)
                self._queue.task_done()

    async def _evaluate(self, submission_id: int, evaluation_version: int) -> None:
        submission = await self.repository.get(submission_id)
        if (
            submission is None
            or submission.status is not SubmissionStatus.PENDING
            or submission.evaluation_version != evaluation_version
        ):
            return
        try:
            await self.problem_service.get_problem(submission.problem_id)
            await self.language_service.get_enabled(submission.language)
            result = await self._judge_service().judge(
                JudgeRequest(
                    problem_id=submission.problem_id,
                    language=submission.language,
                    code=submission.code,
                )
            )
            limit = self.settings.submission_result_limit_bytes
            bounded_result = result.model_copy(
                update={
                    "compile_info": _bounded(result.compile_info, limit),
                    "stdout": _bounded(result.stdout, limit) or "",
                    "stderr": _bounded(result.stderr, limit) or "",
                    "testcase_results": [
                        item.model_copy(
                            update={"error_summary": _bounded(item.error_summary, 512) or ""}
                        )
                        for item in result.testcase_results
                    ],
                }
            )
            await self.repository.complete_if_current(
                submission_id, evaluation_version, bounded_result, _utc_now()
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Submission evaluation failed for %s", submission_id)
            await self.repository.fail_if_current(
                submission_id,
                evaluation_version,
                "evaluation task failed",
                _utc_now(),
            )
