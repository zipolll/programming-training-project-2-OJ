"""Asynchronous JSON-file persistence for problem configurations."""

import asyncio
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.app.modules.problems.models import Problem, ProblemId

_problem_id_adapter = TypeAdapter(ProblemId)


def validate_problem_id(problem_id: str) -> None:
    """Reject identifiers that could escape or alter the storage directory."""
    try:
        _problem_id_adapter.validate_python(problem_id, strict=True)
    except ValidationError as exc:
        raise ValueError("invalid problem id") from exc


class ProblemRepository:
    """Store each problem in one validated, atomically replaced JSON file."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await asyncio.to_thread(self.directory.mkdir, parents=True, exist_ok=True)

    def _path(self, problem_id: str) -> Path:
        validate_problem_id(problem_id)
        return self.directory / f"{problem_id}.json"

    @staticmethod
    def _read_sync(path: Path) -> Problem | None:
        try:
            with path.open(encoding="utf-8") as problem_file:
                return Problem.model_validate(json.load(problem_file))
        except FileNotFoundError:
            return None

    @staticmethod
    def _write_sync(path: Path, problem: Problem) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as temp_file:
                json.dump(
                    problem.model_dump(mode="json", exclude_unset=True),
                    temp_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)
            raise

    async def list_all(self) -> list[Problem]:
        def read_all() -> list[Problem]:
            paths = sorted(self.directory.glob("*.json"), key=lambda path: path.name)
            problems = [self._read_sync(path) for path in paths]
            return sorted(
                (problem for problem in problems if problem is not None),
                key=lambda problem: problem.id,
            )

        async with self._write_lock:
            return await asyncio.to_thread(read_all)

    async def get(self, problem_id: str) -> Problem | None:
        async with self._write_lock:
            return await asyncio.to_thread(self._read_sync, self._path(problem_id))

    async def create(self, problem: Problem) -> bool:
        path = self._path(problem.id)
        async with self._write_lock:
            if await asyncio.to_thread(path.exists):
                return False
            await asyncio.to_thread(self._write_sync, path, problem)
            return True

    async def update(self, problem_id: str, problem: Problem) -> bool:
        path = self._path(problem_id)
        async with self._write_lock:
            if not await asyncio.to_thread(path.is_file):
                return False
            await asyncio.to_thread(self._write_sync, path, problem)
            return True

    async def delete(self, problem_id: str) -> bool:
        path = self._path(problem_id)
        async with self._write_lock:
            try:
                await asyncio.to_thread(path.unlink)
            except FileNotFoundError:
                return False
            return True
