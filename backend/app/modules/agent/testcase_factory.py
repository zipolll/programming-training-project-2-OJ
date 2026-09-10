"""Materialize large-scale AI testcases from generator and reference programs.

The model never writes huge literal test arrays (the output-token budget makes
that impossible). Instead it returns a small Python generator program plus per
case seeds; this module executes that program to synthesize each stdin input,
then executes the reference solution to derive the expected output.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.modules.agent.models import GeneratedProblem, TestCaseGenerator
from backend.app.modules.judge.comparator import OutputDecodeError, decode_output
from backend.app.modules.judge.executor import JudgeExecutor
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.models import TestcaseStatus

GENERATOR_TIME_LIMIT_SECONDS = 20.0
GENERATOR_MEMORY_LIMIT_MB = 512
MAX_GENERATED_INPUT_BYTES = 8 * 1024 * 1024
# Comfortable margin under the default 64 KiB stdout capture limit, so a
# correct solution can never be truncated into a wrong answer.
DEFAULT_OUTPUT_BUDGET_BYTES = 60_000
ERROR_EXCERPT_CHARS = 500

# Runs with `python -I`; -I does not add the script directory to sys.path,
# so the runner inserts its own directory before importing the generator.
_RUNNER_SOURCE = """\
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generator as _generator

spec = json.loads(sys.stdin.read())
text = _generator.build_case(spec)
if not isinstance(text, str):
    sys.stderr.write("build_case must return str, got %r\\n" % type(text).__name__)
    sys.exit(3)
# Bytes-mode write keeps LF endings regardless of host platform.
sys.stdout.buffer.write(text.encode("utf-8"))
"""


def _excerpt(text: str) -> str:
    return text.strip()[:ERROR_EXCERPT_CHARS]


async def run_generator_cases(
    generator: TestCaseGenerator, python_executable: str
) -> tuple[list[str | None], list[str], list[dict]]:
    """Execute the generator once per case spec; return inputs, errors, evidence."""
    executor = JudgeExecutor(output_limit=MAX_GENERATED_INPUT_BYTES)
    inputs: list[str | None] = []
    errors: list[str] = []
    evidence: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="oj-agent-generator-") as directory:
        workspace = Path(directory)
        (workspace / "generator.py").write_text(generator.source, encoding="utf-8")
        (workspace / "_oj_runner.py").write_text(_RUNNER_SOURCE, encoding="utf-8")
        for case in generator.cases:
            spec = {"label": case.label, "seed": case.seed, "params": case.params}
            outcome = await executor.execute(
                [python_executable, "-I", str(workspace / "_oj_runner.py")],
                cwd=str(workspace),
                stdin=json.dumps(spec).encode("utf-8"),
                time_limit=GENERATOR_TIME_LIMIT_SECONDS,
                memory_limit_mb=GENERATOR_MEMORY_LIMIT_MB,
            )
            entry = {"label": case.label, "seed": case.seed, "time": round(outcome.time, 3)}
            if outcome.status is TestcaseStatus.TLE:
                errors.append(
                    f"testcase_generator timed out on case '{case.label}' after "
                    f"{GENERATOR_TIME_LIMIT_SECONDS:.0f}s; the generator must be fast "
                    "and terminate without waiting on time or input"
                )
                inputs.append(None)
            elif outcome.status is TestcaseStatus.MLE:
                errors.append(
                    f"testcase_generator exceeded {GENERATOR_MEMORY_LIMIT_MB} MB memory "
                    f"on case '{case.label}'"
                )
                inputs.append(None)
            elif outcome.returncode:
                message = _excerpt(outcome.stderr.decode("utf-8", errors="replace"))
                errors.append(
                    f"testcase_generator crashed on case '{case.label}' (exit "
                    f"{outcome.returncode}): {message or 'no stderr output'}"
                )
                inputs.append(None)
            elif outcome.stdout_truncated:
                errors.append(
                    f"testcase_generator produced more than "
                    f"{MAX_GENERATED_INPUT_BYTES} bytes on case '{case.label}'; "
                    "reduce the data scale"
                )
                inputs.append(None)
            else:
                try:
                    text = outcome.stdout.decode("utf-8")
                except UnicodeDecodeError:
                    errors.append(
                        f"testcase_generator output is not valid UTF-8 on case "
                        f"'{case.label}'"
                    )
                    inputs.append(None)
                else:
                    if not text.strip():
                        errors.append(
                            f"testcase_generator returned empty input on case "
                            f"'{case.label}'"
                        )
                        inputs.append(None)
                    else:
                        inputs.append(text)
                        entry["input_bytes"] = len(outcome.stdout)
            entry["ok"] = inputs[-1] is not None
            if not entry["ok"]:
                entry["error"] = errors[-1]
            evidence.append(entry)
    return inputs, errors, evidence


async def run_reference_for_outputs(
    generated: GeneratedProblem,
    inputs: list[str | None],
    language_service: LanguageService,
    settings: Settings,
) -> tuple[list[str | None], list[str], list[dict]]:
    """Run the reference solution once per generated input to derive outputs."""
    problem = generated.problem
    language = await language_service.get_enabled(generated.reference_solution_language)
    output_limit = problem.output_limit_bytes or settings.judge_output_limit_bytes
    executor = JudgeExecutor(output_limit=settings.judge_output_limit_bytes)
    outputs: list[str | None] = []
    errors: list[str] = []
    evidence: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="oj-agent-expected-") as directory:
        workspace = Path(directory)
        source = workspace / f"main{language.file_ext}"
        executable = workspace / ("program.exe" if os.name == "nt" else "program")
        source.write_text(generated.reference_solution, encoding="utf-8")
        command = language.expand_run(source, executable)
        compile_info = None
        compile_command = language.expand_compile(source, executable)
        if compile_command is not None:
            compiled = await executor.execute(
                compile_command,
                cwd=str(workspace),
                stdin=b"",
                time_limit=settings.judge_compile_timeout_seconds,
                memory_limit_mb=settings.judge_compile_memory_limit_mb,
            )
            compile_info = compiled.stderr.decode("utf-8", errors="replace")[
                :ERROR_EXCERPT_CHARS
            ]
            if compiled.status is not None:
                return (
                    [None] * len(inputs),
                    [f"reference solution failed to compile: {compile_info or 'unknown error'}"],
                    [{"ok": False, "stage": "compile", "error": compile_info}],
                )
        for index, case_input in enumerate(inputs, start=1):
            if case_input is None:
                outputs.append(None)
                continue
            outcome = await executor.execute(
                command,
                cwd=str(workspace),
                stdin=case_input.encode("utf-8"),
                time_limit=problem.time_limit,
                memory_limit_mb=problem.memory_limit,
                output_limit=output_limit,
            )
            entry = {"case": index, "time": round(outcome.time, 3)}
            if outcome.status is TestcaseStatus.TLE:
                errors.append(
                    f"reference solution timed out ({problem.time_limit:.1f}s limit) on "
                    f"generated case #{index}; the intended algorithm must be fast "
                    "enough on the declared maximum data scale"
                )
                outputs.append(None)
            elif outcome.returncode:
                message = _excerpt(outcome.stderr.decode("utf-8", errors="replace"))
                errors.append(
                    f"reference solution crashed on generated case #{index} (exit "
                    f"{outcome.returncode}): {message or 'no stderr output'}"
                )
                outputs.append(None)
            elif outcome.stdout_truncated:
                errors.append(
                    f"expected output of generated case #{index} exceeds the capture "
                    f"limit of {output_limit} bytes; bound the output volume (fewer "
                    "answer lines or aggregated output) or declare a larger "
                    "problem.output_limit_bytes"
                )
                outputs.append(None)
            else:
                try:
                    # Normalize CRLF so stored expectations stay portable; the
                    # judge comparator already treats line endings loosely.
                    outputs.append(decode_output(outcome.stdout).replace("\r\n", "\n"))
                    entry["output_bytes"] = len(outcome.stdout)
                except OutputDecodeError:
                    errors.append(
                        f"reference solution output is not valid UTF-8 on generated "
                        f"case #{index}"
                    )
                    outputs.append(None)
            entry["ok"] = outputs[-1] is not None
            if not entry["ok"]:
                entry["error"] = errors[-1]
            evidence.append(entry)
        if compile_info:
            evidence.insert(0, {"ok": True, "stage": "compile", "info": compile_info})
    return outputs, errors, evidence


async def python_executable(language_service: LanguageService) -> str:
    try:
        config = await language_service.get_enabled("python")
    except Exception:
        return sys.executable
    return config.run_args[0]


__all__ = [
    "DEFAULT_OUTPUT_BUDGET_BYTES",
    "MAX_GENERATED_INPUT_BYTES",
    "python_executable",
    "run_generator_cases",
    "run_reference_for_outputs",
]
