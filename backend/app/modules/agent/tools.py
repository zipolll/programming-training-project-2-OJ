"""Fixed, bounded tool registry for the authoring agent."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.modules.agent import testcase_factory
from backend.app.modules.agent.models import GeneratedProblem, ValidationReport
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.models import JudgeRequest, TestcaseStatus
from backend.app.modules.judge.service import JudgeService
from backend.app.modules.problems.models import Problem, Testcase
from backend.app.modules.problems.repository import ProblemRepository
from backend.app.modules.problems.service import ProblemService

# A stress testcase below this size cannot credibly separate algorithms.
STRESS_MIN_INPUT_BYTES = 50_000


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
            "testcases": [
                {
                    **item.model_dump(mode="json"),
                    **(
                        {"actual_output": item.actual_output}
                        if item.result is not TestcaseStatus.AC
                        else {}
                    ),
                }
                for item in result.testcase_results
            ],
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

    async def evaluate_counterexamples(self, generated: GeneratedProblem) -> dict[str, Any]:
        detections: dict[str, list[int]] = {}
        tle_cases: dict[str, list[int]] = {}
        for index, code in enumerate(generated.wrong_solutions[:5], start=1):
            result = await self._judge(
                generated.problem, generated.reference_solution_language, code
            )
            detections[f"wrong_{index}"] = [
                item.id for item in result.testcase_results if item.result is not TestcaseStatus.AC
            ]
            tle_cases[f"wrong_{index}"] = [
                item.id for item in result.testcase_results if item.result is TestcaseStatus.TLE
            ]
            if result.status is TestcaseStatus.CE and not detections[f"wrong_{index}"]:
                detections[f"wrong_{index}"] = [0]
        return {
            "run": len(detections),
            "detections": detections,
            "tle_cases": tle_cases,
        }

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

    async def materialize_testcases(
        self, generated: GeneratedProblem
    ) -> tuple[GeneratedProblem, ValidationReport | None]:
        """Execute the draft's testcase generator and derive expected outputs.

        Returns the updated draft plus a report when any generator or reference
        run failed; on success the generator field is consumed and the produced
        cases are appended to the problem's testcases.
        """
        generator = generated.testcase_generator
        if generator is None:
            return generated, None
        executable = await testcase_factory.python_executable(self.language_service)
        inputs, errors, generator_evidence = await testcase_factory.run_generator_cases(
            generator, executable
        )
        outputs: list[str | None] = []
        reference_evidence: list[dict[str, Any]] = []
        if any(case_input is not None for case_input in inputs):
            outputs, reference_errors, reference_evidence = (
                await testcase_factory.run_reference_for_outputs(
                    generated, inputs, self.language_service, self.settings
                )
            )
            errors.extend(reference_errors)
        cases = [
            Testcase(input=case_input, output=case_output)
            # Non-strict zip: outputs stays empty when every generator run failed.
            for case_input, case_output in zip(inputs, outputs, strict=False)
            if case_input is not None and case_output is not None
        ]
        problem = generated.problem.model_copy(
            update={"testcases": [*generated.problem.testcases, *cases]}
        )
        if errors:
            report = ValidationReport(
                schema_valid=True,
                testcase_count=len(problem.testcases),
                blocking_errors=errors,
                tool_evidence=[
                    {
                        "tool": "materialize_testcases",
                        "result": {
                            "generator": generator_evidence,
                            "reference": reference_evidence,
                        },
                    }
                ],
            )
            # Keep the generator so the revision loop still sees the failing spec.
            return generated.model_copy(update={"problem": problem}), report
        return (
            generated.model_copy(
                update={"problem": problem, "testcase_generator": None}
            ),
            None,
        )

    async def build_validation_report(
        self,
        generated: GeneratedProblem,
        *,
        reference_only: bool = False,
        stress_testing: bool = False,
    ) -> ValidationReport:
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
        ]
        if not reference_only:
            jobs.append(asyncio.create_task(self.evaluate_counterexamples(generated)))
        try:
            results = await asyncio.gather(*jobs)
            reference = results[0]
            counterexamples = results[1] if len(results) > 1 else {"run": 0, "detections": {}}
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
        for group, original in (
            (samples, generated.problem.samples),
            (tests, generated.problem.testcases),
        ):
            for result, case in zip(group["testcases"], original, strict=False):
                if result["result"] != "AC":
                    result["input"] = case.input[:2000]
                    result["expected_output"] = case.output[:2000]
                    result["diagnostics_truncated"] = any(
                        len(text) >= 2000
                        for text in (case.input, case.output, result.get("actual_output", ""))
                    )

        def failure_details(results: list[dict[str, Any]], expected: list[str]) -> str:
            details = []
            for position, item in enumerate(results):
                if item["result"] == "AC" or position >= len(expected):
                    continue
                wanted = str(expected[position]).strip()
                if len(wanted) > 60:
                    wanted = wanted[:60] + "…"
                details.append(f"case #{position + 1} {item['result']} expected {wanted!r}")
            return "; ".join(details[:5]) or "no per-case result available"

        sample_outputs = [s.output for s in generated.problem.samples]
        case_outputs = [c.output for c in generated.problem.testcases]
        if reference_only:
            blocking = []
            if not samples["consistent"]:
                blocking.append(
                    "参考程序未通过样例：" + failure_details(samples["testcases"], sample_outputs)
                )
            if not tests["all_passed"]:
                blocking.append(
                    "参考程序未通过测试点：" + failure_details(tests["testcases"], case_outputs)
                )
            return ValidationReport(
                schema_valid=schema["valid"],
                reference_all_passed=tests["all_passed"],
                samples_consistent=samples["consistent"],
                testcase_count=len(generated.problem.testcases),
                blocking_errors=blocking,
                tool_evidence=[
                    {"tool": "validate_sample_outputs", "result": samples},
                    {"tool": "validate_testcases", "result": tests},
                ],
            )
        coverage = await self.analyze_test_coverage(generated.problem)
        blocking = []
        if not schema["valid"]:
            blocking.append("problem schema is invalid")
        if not samples["consistent"]:
            blocking.append(
                "sample outputs do not match the reference solution: "
                + failure_details(samples["testcases"], sample_outputs)
            )
        if not tests["all_passed"]:
            blocking.append(
                "reference solution does not pass every testcase: "
                + failure_details(tests["testcases"], case_outputs)
            )
        if len(generated.problem.testcases) < 3:
            blocking.append("at least three testcases are required for AI import")
        detections = counterexamples["detections"]
        distinguishes = bool(detections) and all(detections.values())
        risks = []
        slowest = max((item.get("time") or 0 for item in tests["testcases"]), default=0)
        if slowest > generated.problem.time_limit * 0.8:
            risks.append(
                f"reference solution takes {slowest:.2f}s of the "
                f"{generated.problem.time_limit:.1f}s limit on the slowest case; "
                "reduce complexity or it may time out after import"
            )
        if not detections:
            risks.append("no counterexample solution was supplied")
        elif not distinguishes:
            blocking.append("one or more wrong solutions are not detected")
        if stress_testing:
            if coverage["maximum_input_bytes"] < STRESS_MIN_INPUT_BYTES:
                blocking.append(
                    f"strong data not achieved: the largest testcase input is only "
                    f"{coverage['maximum_input_bytes']} bytes (at least "
                    f"{STRESS_MIN_INPUT_BYTES} required); use testcase_generator to "
                    "produce maximum-scale stress cases"
                )
            if not any(counterexamples["tle_cases"].values()):
                blocking.append(
                    "strong data not achieved: no wrong solution times out (TLE) on "
                    "any testcase; include the intended-to-reject brute force as a "
                    "wrong solution and enlarge the max-scale generated cases until "
                    "it exceeds the time limit while the reference stays well below it"
                )
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
            wrong_solution_tle_cases=counterexamples["tle_cases"],
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
