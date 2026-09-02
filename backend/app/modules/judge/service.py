"""Reusable asynchronous judge orchestration for future submission workers."""

import asyncio
import os
import tempfile
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.modules.judge.comparator import OutputDecodeError, decode_output, outputs_match
from backend.app.modules.judge.executor import JudgeExecutor, ProcessOutcome
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.models import (
    JudgeRequest,
    JudgeResult,
    TestcaseResult,
    TestcaseStatus,
)
from backend.app.modules.problems.service import ProblemService


class JudgeService:
    """Compile once and execute every testcase in an isolated temporary directory."""

    def __init__(
        self,
        problem_service: ProblemService,
        language_service: LanguageService,
        settings: Settings,
        executor: JudgeExecutor | None = None,
    ) -> None:
        self.problem_service = problem_service
        self.language_service = language_service
        self.settings = settings
        self.executor = executor or JudgeExecutor(settings.judge_output_limit_bytes)
        self._validate_temp_root(settings.judge_temp_root)

    async def judge(self, request: JudgeRequest) -> JudgeResult:
        """Judge a request; known missing resources remain service-level errors."""
        problem = await self.problem_service.get_problem(request.problem_id)
        language = await self.language_service.get_enabled(request.language)
        root = self.settings.judge_temp_root
        if root is not None:
            await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory(dir=root, prefix="oj-judge-") as temporary_name:
                workspace = Path(temporary_name)
                source = workspace / f"main{language.file_ext}"
                executable = workspace / ("program.exe" if os.name == "nt" else "program")
                await asyncio.to_thread(source.write_text, request.code, encoding="utf-8")

                compile_info = None
                compile_command = language.expand_compile(source, executable)
                if compile_command is not None:
                    compiled = await self.executor.execute(
                        compile_command,
                        cwd=str(workspace),
                        stdin=b"",
                        time_limit=self.settings.judge_compile_timeout_seconds,
                        memory_limit_mb=self.settings.judge_compile_memory_limit_mb,
                    )
                    compile_info = self._compile_message(compiled, workspace)
                    if compiled.status is not None:
                        return self._compile_failure(compiled, compile_info)

                results: list[TestcaseResult] = []
                captured_stdout = ""
                captured_stderr = ""
                for testcase_id, testcase in enumerate(problem.testcases, start=1):
                    result, stdout, stderr = await self._judge_testcase(
                        testcase_id,
                        testcase.input,
                        testcase.output,
                        language.expand_run(source, executable),
                        workspace,
                        problem.time_limit or language.time_limit,
                        problem.memory_limit or language.memory_limit,
                    )
                    results.append(result)
                    captured_stdout = self._bounded_join(captured_stdout, stdout)
                    captured_stderr = self._bounded_join(captured_stderr, stderr)

                overall = next(
                    (item.result for item in results if item.result is not TestcaseStatus.AC),
                    TestcaseStatus.AC,
                )
                return JudgeResult(
                    status=overall,
                    score=sum(10 for item in results if item.result is TestcaseStatus.AC),
                    compile_info=compile_info,
                    stdout=captured_stdout,
                    stderr=captured_stderr,
                    time=sum(item.time for item in results),
                    memory=max((item.memory for item in results), default=0.0),
                    testcase_results=results,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            return JudgeResult(
                status=TestcaseStatus.UNK,
                score=0,
                stderr=self._safe_summary(str(exc), None),
                time=0,
                memory=0,
            )

    async def _judge_testcase(
        self,
        testcase_id: int,
        testcase_input: str,
        expected_output: str,
        command: list[str],
        workspace: Path,
        time_limit: float,
        memory_limit: int,
    ) -> tuple[TestcaseResult, str, str]:
        try:
            outcome = await self.executor.execute(
                command,
                cwd=str(workspace),
                stdin=testcase_input.encode("utf-8"),
                time_limit=time_limit,
                memory_limit_mb=memory_limit,
            )
            stdout = decode_output(outcome.stdout)
            stderr = outcome.stderr.decode("utf-8", errors="replace")
            status = outcome.status
            memory_error_markers = ("MemoryError", "bad_alloc", "Cannot allocate memory")
            if status is TestcaseStatus.RE and any(
                marker in stderr for marker in memory_error_markers
            ):
                status = TestcaseStatus.MLE
            if status is None:
                status = (
                    TestcaseStatus.WA
                    if outcome.stdout_truncated or not outputs_match(stdout, expected_output)
                    else TestcaseStatus.AC
                )
            summary = self._result_summary(status, outcome, stderr, workspace)
            return (
                TestcaseResult(
                    id=testcase_id,
                    result=status,
                    time=outcome.time,
                    memory=outcome.memory,
                    error_summary=summary,
                ),
                stdout,
                stderr,
            )
        except OutputDecodeError as exc:
            summary = str(exc)
        except (OSError, RuntimeError, ValueError) as exc:
            summary = self._safe_summary(str(exc), workspace)
        return (
            TestcaseResult(
                id=testcase_id,
                result=TestcaseStatus.UNK,
                time=0,
                memory=0,
                error_summary=summary,
            ),
            "",
            summary,
        )

    def _compile_message(self, outcome: ProcessOutcome, workspace: Path) -> str:
        message = outcome.stderr.decode("utf-8", errors="replace")
        if not message:
            message = outcome.stdout.decode("utf-8", errors="replace")
        if outcome.status is None:
            return "success"
        if outcome.status is TestcaseStatus.TLE:
            message = "compilation timed out"
        elif outcome.status is TestcaseStatus.MLE:
            message = "compilation exceeded memory limit"
        elif not message:
            message = (
                "compiler could not be started"
                if outcome.returncode is None
                else "compilation failed"
            )
        return self._safe_summary(message, workspace, self.settings.judge_output_limit_bytes)

    @staticmethod
    def _compile_failure(outcome: ProcessOutcome, compile_info: str) -> JudgeResult:
        return JudgeResult(
            status=TestcaseStatus.CE,
            score=0,
            compile_info=compile_info,
            time=outcome.time,
            memory=outcome.memory,
        )

    def _result_summary(
        self,
        status: TestcaseStatus,
        outcome: ProcessOutcome,
        stderr: str,
        workspace: Path,
    ) -> str:
        if status is TestcaseStatus.TLE:
            return "time limit exceeded"
        if status is TestcaseStatus.MLE:
            return "memory limit exceeded"
        if outcome.stdout_truncated:
            return "stdout exceeded capture limit"
        if outcome.stderr_truncated:
            return "stderr exceeded capture limit"
        if status is TestcaseStatus.RE:
            return self._safe_summary(stderr or "process exited with an error", workspace)
        return ""

    def _bounded_join(self, current: str, addition: str) -> str:
        combined = addition if not current else f"{current}\n{addition}"
        encoded = combined.encode("utf-8")[: self.settings.judge_output_limit_bytes]
        return encoded.decode("utf-8", errors="ignore")

    @staticmethod
    def _validate_temp_root(root: Path | None) -> None:
        if root is None:
            return
        project_root = Path(__file__).resolve().parents[4]
        if root.resolve().is_relative_to(project_root):
            raise ValueError("judge temporary root must be outside the project source tree")

    @staticmethod
    def _safe_summary(message: str, workspace: Path | None, limit: int = 512) -> str:
        if workspace is not None:
            message = message.replace(str(workspace), "<judge-workspace>")
        return message[:limit]
