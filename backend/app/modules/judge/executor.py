"""Safe-by-default asynchronous compilation and process execution."""

import asyncio
import os
import time
from contextlib import suppress
from dataclasses import dataclass

from backend.app.modules.judge.models import TestcaseStatus
from backend.app.modules.judge.resource_limiter import ResourceLimiter, get_resource_limiter


@dataclass(frozen=True)
class ProcessOutcome:
    status: TestcaseStatus | None
    returncode: int | None
    stdout: bytes
    stderr: bytes
    time: float
    memory: float
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class JudgeExecutor:
    def __init__(self, output_limit: int, limiter: ResourceLimiter | None = None) -> None:
        self.output_limit = output_limit
        self.limiter = limiter or get_resource_limiter()

    async def execute(
        self,
        arguments: list[str],
        *,
        cwd: str,
        stdin: bytes,
        time_limit: float,
        memory_limit_mb: int,
        output_limit: int | None = None,
    ) -> ProcessOutcome:
        """Execute an argument vector with bounded output, time, and memory."""
        capture_limit = output_limit or self.output_limit
        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *arguments,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_safe_environment(),
                **self.limiter.subprocess_options(memory_limit_mb, time_limit),
            )
        except (OSError, ValueError):
            return ProcessOutcome(TestcaseStatus.UNK, None, b"", b"", 0.0, 0.0)

        stdout_task = asyncio.create_task(self._read_limited(process.stdout, capture_limit))
        stderr_task = asyncio.create_task(self._read_limited(process.stderr, capture_limit))
        stdin_task = asyncio.create_task(self._write_stdin(process, stdin))
        wait_task = asyncio.create_task(process.wait())
        memory_task = asyncio.create_task(self._monitor_memory(process, memory_limit_mb))
        timeout_task = asyncio.create_task(asyncio.sleep(time_limit))
        status: TestcaseStatus | None = None
        peak_memory = 0
        try:
            done, _ = await asyncio.wait(
                {wait_task, memory_task, timeout_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if timeout_task in done and process.returncode is None:
                status = TestcaseStatus.TLE
                await self.limiter.terminate_tree(process.pid)
            elif memory_task in done:
                exceeded, peak_memory = memory_task.result()
                if exceeded:
                    status = TestcaseStatus.MLE
                    if process.returncode is None:
                        await self.limiter.terminate_tree(process.pid)
            await process.wait()
            if not memory_task.done():
                _, peak_memory = await memory_task
        except BaseException:
            await self.limiter.terminate_tree(process.pid)
            with suppress(ProcessLookupError):
                await process.wait()
            raise
        finally:
            timeout_task.cancel()
            if not memory_task.done():
                memory_task.cancel()
            await asyncio.gather(timeout_task, memory_task, return_exceptions=True)

        await asyncio.gather(stdin_task, return_exceptions=True)
        stdout, stdout_truncated = await stdout_task
        stderr, stderr_truncated = await stderr_task
        elapsed = time.perf_counter() - started
        if status is None and process.returncode:
            status = TestcaseStatus.RE
        return ProcessOutcome(
            status=status,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            time=elapsed,
            memory=peak_memory / (1024 * 1024),
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    async def _read_limited(
        self, stream: asyncio.StreamReader | None, output_limit: int
    ) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        collected = bytearray()
        truncated = False
        while chunk := await stream.read(8192):
            remaining = output_limit - len(collected)
            if remaining > 0:
                collected.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        return bytes(collected), truncated

    @staticmethod
    async def _write_stdin(process: asyncio.subprocess.Process, content: bytes) -> None:
        if process.stdin is None:
            return
        try:
            process.stdin.write(content)
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await process.stdin.wait_closed()

    async def _monitor_memory(
        self, process: asyncio.subprocess.Process, memory_limit_mb: int
    ) -> tuple[bool, int]:
        limit_bytes = memory_limit_mb * 1024 * 1024
        peak = 0
        while process.returncode is None:
            usage = await self.limiter.memory_usage_bytes(process.pid)
            peak = max(peak, usage)
            if usage > limit_bytes:
                return True, peak
            await asyncio.sleep(0.01)
        return False, peak


def _safe_environment() -> dict[str, str]:
    """Pass only runtime essentials, never application secrets, to user code."""
    allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    return environment
