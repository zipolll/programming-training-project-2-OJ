"""Problem-management business rules."""

from backend.app.modules.problems.models import Problem, ProblemSummary
from backend.app.modules.problems.repository import ProblemRepository, validate_problem_id


class ProblemNotFoundError(Exception):
    """Raised when a requested problem does not exist."""


class ProblemAlreadyExistsError(Exception):
    """Raised when creation would overwrite an existing problem."""


class ProblemIdMismatchError(Exception):
    """Raised when an update body targets a different problem id."""


class ProblemService:
    def __init__(self, repository: ProblemRepository) -> None:
        self.repository = repository

    async def initialize(self) -> None:
        await self.repository.initialize()

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
        if not await self.repository.create(problem):
            raise ProblemAlreadyExistsError

    async def update_problem(self, problem_id: str, problem: Problem) -> None:
        validate_problem_id(problem_id)
        if problem.id != problem_id:
            raise ProblemIdMismatchError
        if not await self.repository.update(problem_id, problem):
            raise ProblemNotFoundError

    async def delete_problem(self, problem_id: str) -> None:
        validate_problem_id(problem_id)
        if not await self.repository.delete(problem_id):
            raise ProblemNotFoundError
