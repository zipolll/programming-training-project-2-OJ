"""Fixed, bounded tool registry for the authoring agent."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.modules.agent.models import GeneratedProblem, ValidationReport
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.models import JudgeRequest, TestcaseStatus
from backend.app.modules.judge.service import JudgeService
from backend.app.modules.problems.models import Problem, Testcase
from backend.app.modules.problems.repository import ProblemRepository
from backend.app.modules.problems.service import ProblemService


class AgentToolError(RuntimeError):
    pass


class AgentTools:
    """Expose only named problem-bank and judge operations; never shell or arbitrary I/O."""

    names = frozenset(
        {
            "search_problem_bank",
            "validate_problem_schema",
            "execute_reference_solution",
            "validate_sample_outputs",
            "validate_testcases",
            "evaluate_counterexamples",
            "analyze_test_coverage",
        }
    )

    def __init__(
        self,
        problem_service: ProblemService,
        language_service: LanguageService,
        settings: Settings,
    ) -> None:
        self.problem_service = problem_service
        self.language_service = language_service
        self.settings = settings
        self._judge_slots = asyncio.Semaphore(2)

    async def search_problem_bank(
        self, terms: list[str], difficulty: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        query = {item.casefold() for item in terms if item.strip()}
        scored = []
        for problem in await self.problem_service.list_problems():
            haystack = {problem.title.casefold(), problem.difficulty.casefold()}
            haystack.update(tag.casefold() for tag in problem.tags)
            same_difficulty = problem.difficulty.casefold() == difficulty.casefold()
            score = len(query & haystack) + int(same_difficulty)
            if score:
                scored.append((score, problem))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        selected = [
            await self.problem_service.get_problem(item.id) for _, item in scored[: min(limit, 10)]
        ]
        return [
            {
                "id": item.id,
                "title": item.title,
                "difficulty": item.difficulty,
                "tags": item.tags[:10],
                "description_excerpt": item.description[:300],
            }
            for item in selected
        ]

    @staticmethod
    async def validate_problem_schema(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            Problem.model_validate(payload)
        except ValidationError as exc:
            return {
                "valid": False,
                "errors": [
                    {"path": list(error["loc"]), "reason": error["msg"]}
                    for error in exc.errors()[:50]
                ],
            }
        return {"valid": True, "errors": []}

    async def execute_reference_solution(
        self, generated: GeneratedProblem, problem: Problem | None = None
    ) -> dict[str, Any]:
        target = problem or generated.problem
        result = await self._judge(
            target, generated.reference_solution_language, generated.reference_solution
        )
        return {
            "status": result.status.value,
            "testcases": [item.model_dump(mode="json") for item in result.testcase_results],
            "compile_info": result.compile_info,
        }

    async def validate_sample_outputs(self, generated: GeneratedProblem) -> dict[str, Any]:
        problem = generated.problem.model_copy(
            update={
                "testcases": [
                    Testcase(input=sample.input, output=sample.output)
                    for sample in generated.problem.samples
                ]
            }
        )
        result = await self.execute_reference_solution(generated, problem)
        return {"consistent": result["status"] == "AC", **result}

    async def validate_testcases(self, generated: GeneratedProblem) -> dict[str, Any]:
        result = await self.execute_reference_solution(generated)
        return {"all_passed": result["status"] == "AC", **result}

    async def evaluate_counterexamples(self, generated: GeneratedProblem) -> dict[str, Any]:
        detections: dict[str, list[int]] = {}
        for index, code in enumerate(generated.wrong_solutions[:5], start=1):
            result = await self._judge(
                generated.problem, generated.reference_solution_language, code
            )
            detections[f"wrong_{index}"] = [
                item.id for item in result.testcase_results if item.result is not TestcaseStatus.AC
            ]
            if result.status is TestcaseStatus.CE and not detections[f"wrong_{index}"]:
                detections[f"wrong_{index}"] = [0]
        return {"run": len(detections), "detections": detections}

    @staticmethod
    async def analyze_test_coverage(problem: Problem) -> dict[str, Any]:
        inputs = [case.input.strip() for case in problem.testcases]
        joined = "\n".join(inputs)
        boundary = []
        if any(value in joined.split() for value in ("0", "1", "-1")):
            boundary.append("minimum_or_identity")
        if len(set(inputs)) < len(inputs):
            boundary.append("duplicate_case")
        if any(len(value.split()) <= 2 for value in inputs):
            boundary.append("single_or_small")
        sizes = [len(value.encode()) for value in inputs]
        if sizes and max(sizes) >= 1000:
            boundary.append("large_input")
        return {
            "boundary_types": boundary,
            "random_or_combinatorial": len(set(inputs)) >= min(5, len(inputs)),
            "maximum_input_bytes": max(sizes, default=0),
        }

    async def build_validation_report(self, generated: GeneratedProblem) -> ValidationReport:
        schema = await self.validate_problem_schema(generated.problem.model_dump(mode="json"))
        # Compile the reference once and reuse identical sample/test input-output pairs.
        cases = list(generated.problem.testcases)
        sample_indexes = []
        for sample in generated.problem.samples:
            case = Testcase(input=sample.input, output=sample.output)
            if case not in cases:
                cases.append(case)
            sample_indexes.append(cases.index(case))
        jobs = [
            asyncio.create_task(
                self.execute_reference_solution(
                    generated,
                    generated.problem.model_copy(update={"testcases": cases}),
                )
            ),
            asyncio.create_task(self.evaluate_counterexamples(generated)),
        ]
        try:
            reference, counterexamples = await asyncio.gather(*jobs)
        finally:
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)

        def subset(indexes):
            results = [
                reference["testcases"][i] for i in indexes if i < len(reference["testcases"])
            ]
            passed = len(results) == len(indexes) and all(r["result"] == "AC" for r in results)
            return {
                "status": "AC"
                if passed
                else reference["status"]
                if reference["status"] != "AC"
                else "UNK",
                "testcases": results,
                "compile_info": reference["compile_info"],
            }

        samples = subset(sample_indexes)
        samples["consistent"] = samples["status"] == "AC"
        tests = subset(list(range(len(generated.problem.testcases))))
        tests["all_passed"] = tests["status"] == "AC"
        coverage = await self.analyze_test_coverage(generated.problem)
        blocking = []
        if not schema["valid"]:
            blocking.append("problem schema is invalid")
        if not samples["consistent"]:
            blocking.append("sample outputs do not match the reference solution")
        if not tests["all_passed"]:
            blocking.append("reference solution does not pass every testcase")
        if len(generated.problem.testcases) < 3:
            blocking.append("at least three testcases are required for AI import")
        detections = counterexamples["detections"]
        distinguishes = bool(detections) and all(detections.values())
        risks = []
        if not detections:
            risks.append("no counterexample solution was supplied")
        elif not distinguishes:
            blocking.append("one or more wrong solutions are not detected")
        if "large_input" not in coverage["boundary_types"]:
            risks.append("large-input coverage was not demonstrated")
        return ValidationReport(
            schema_valid=schema["valid"],
            reference_all_passed=tests["all_passed"],
            samples_consistent=samples["consistent"],
            testcase_count=len(generated.problem.testcases),
            boundary_coverage=coverage["boundary_types"],
            random_or_combinatorial_coverage=coverage["random_or_combinatorial"],
            maximum_data_scale=f"{coverage['maximum_input_bytes']} input bytes",
            distinguishes_bruteforce=distinguishes,
            wrong_solutions_run=counterexamples["run"],
            wrong_solution_detections=detections,
            blocking_errors=blocking,
            unresolved_risks=risks,
            tool_evidence=[
                {"tool": "validate_problem_schema", "result": schema},
                {"tool": "validate_sample_outputs", "result": samples},
                {"tool": "validate_testcases", "result": tests},
                {"tool": "evaluate_counterexamples", "result": counterexamples},
                {"tool": "analyze_test_coverage", "result": coverage},
            ],
        )

    async def _judge(self, problem: Problem, language: str, code: str):
        async with self._judge_slots:
            return await self._judge_with_slot(problem, language, code)

    async def _judge_with_slot(self, problem: Problem, language: str, code: str):
        with tempfile.TemporaryDirectory(prefix="oj-agent-problems-") as directory:
            service = ProblemService(ProblemRepository(Path(directory)))
            await service.initialize()
            await service.create_problem(problem)
            judge = JudgeService(service, self.language_service, self.settings)
            return await judge.judge(
                JudgeRequest(problem_id=problem.id, language=language, code=code)
            )


def reject_unknown_tool(name: str) -> None:
    if name not in AgentTools.names:
        raise AgentToolError("model requested an unregistered tool")
