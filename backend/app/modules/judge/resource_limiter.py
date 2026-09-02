"""Platform-specific process isolation and resource-limit adapters."""

import asyncio
import math
import os
import signal
import subprocess
from contextlib import suppress
from typing import Any

import psutil


class ResourceLimiter:
    """Build subprocess options and terminate complete process trees."""

    def subprocess_options(self, memory_limit_mb: int, time_limit: float) -> dict[str, Any]:
        raise NotImplementedError

    async def memory_usage_bytes(self, pid: int) -> int:
        def measure() -> int:
            try:
                process = psutil.Process(pid)
                processes = [process, *process.children(recursive=True)]
                return sum(item.memory_info().rss for item in processes if item.is_running())
            except (psutil.Error, OSError):
                return 0

        return await asyncio.to_thread(measure)

    async def terminate_tree(self, pid: int) -> None:
        await asyncio.to_thread(self._terminate_tree_sync, pid)

    @staticmethod
    def _terminate_tree_sync(pid: int) -> None:
        try:
            process = psutil.Process(pid)
            processes = [*process.children(recursive=True), process]
        except psutil.Error:
            return
        for item in processes:
            with suppress(psutil.Error):
                item.kill()
        with suppress(psutil.Error):
            psutil.wait_procs(processes, timeout=2)


class PosixResourceLimiter(ResourceLimiter):
    def subprocess_options(self, memory_limit_mb: int, time_limit: float) -> dict[str, Any]:
        memory_limit_bytes = memory_limit_mb * 1024 * 1024
        cpu_seconds = max(1, math.ceil(time_limit))

        def apply_limits() -> None:
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))

        return {"start_new_session": True, "preexec_fn": apply_limits}

    @staticmethod
    def _terminate_tree_sync(pid: int) -> None:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)
        ResourceLimiter._terminate_tree_sync(pid)


class WindowsResourceLimiter(ResourceLimiter):
    """Best-effort psutil enforcement; Windows has no resource.setrlimit."""

    def subprocess_options(self, memory_limit_mb: int, time_limit: float) -> dict[str, Any]:
        del memory_limit_mb, time_limit
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        return {"creationflags": flags}


def get_resource_limiter() -> ResourceLimiter:
    return WindowsResourceLimiter() if os.name == "nt" else PosixResourceLimiter()
