"""Problem-management business rules."""

import asyncio

from backend.app.core.database import Database
from backend.app.modules.problems.models import Problem, ProblemSummary
from backend.app.modules.problems.repository import ProblemRepository, validate_problem_id


class ProblemNotFoundError(Exception):
    """Raised when a requested problem does not exist."""


class ProblemAlreadyExistsError(Exception):
    """Raised when creation would overwrite an existing problem."""


class ProblemIdMismatchError(Exception):
    """Raised when an update body targets a different problem id."""


class ProblemService:
    def __init__(self, repository: ProblemRepository, database: Database | None = None) -> None:
        self.repository = repository
        self.database = database
        self.mutation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self.repository.initialize()
        if self.database is not None:
            existing = {problem.id for problem in await self.repository.list_all()}
            async with self.database.connect() as connection:
                rows = await (await connection.execute(
                    "SELECT DISTINCT problem_id FROM submissions WHERE statistics_excluded = 0"
                )).fetchall()
                await connection.executemany(
                    "UPDATE submissions SET statistics_excluded = 1 WHERE problem_id = ?",
                    [(row[0],) for row in rows if row[0] not in existing],
                )
                await connection.commit()

    async def list_problems(self) -> list[ProblemSummary]:
        problems = await self.repository.list_all()
        return [
            ProblemSummary(
                id=problem.id,
                title=problem.title,
                difficulty=problem.difficulty,
                problem_type=problem.problem_type,
                tags=problem.tags,
                source=problem.source,
                author=problem.author,
            )
            for problem in problems
        ]

    async def get_problem(self, problem_id: str) -> Problem:
        validate_problem_id(problem_id)
        problem = await self.repository.get(problem_id)
        if problem is None:
            raise ProblemNotFoundError
        return problem

    async def create_problem(self, problem: Problem) -> None:
        async with self.mutation_lock:
            if not await self.repository.create(problem):
                raise ProblemAlreadyExistsError

    async def update_problem(self, problem_id: str, problem: Problem) -> None:
        validate_problem_id(problem_id)
        if problem.id != problem_id:
            raise ProblemIdMismatchError
        if not await self.repository.update(problem_id, problem):
            raise ProblemNotFoundError

    async def delete_problem(self, problem_id: str) -> None:
        async with self.mutation_lock:
            await self._delete_problem(problem_id)

    async def _delete_problem(self, problem_id: str) -> None:
        validate_problem_id(problem_id)
        if not await self.repository.delete(problem_id):
            raise ProblemNotFoundError
        if self.database is not None:
            async with self.database.connect() as connection:
                await connection.execute(
                    "UPDATE submissions SET statistics_excluded = 1 WHERE problem_id = ?",
                    (problem_id,),
                )
                await connection.execute(
                    "DELETE FROM problem_log_visibility WHERE problem_id = ?", (problem_id,)
                )
                await connection.commit()
