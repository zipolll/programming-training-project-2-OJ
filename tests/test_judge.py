"""Python/C++ judge integration, limits, and cleanup tests."""

import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.judge.models import (
    JudgeRequest,
    JudgeResult,
)
from backend.app.modules.judge.models import (
    TestcaseStatus as Status,
)


@pytest.fixture
def judge_context(tmp_path: Path) -> Iterator[tuple[TestClient, FastAPI, Path]]:
    judge_root = tmp_path / "judge-workspaces"
    settings = Settings(
        database_path=tmp_path / "oj.sqlite3",
        problems_path=tmp_path / "problems",
        judge_temp_root=judge_root,
        judge_output_limit_bytes=4096,
        judge_compile_timeout_seconds=10,
        environment="test",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        assert client.post(
            "/api/users/register", json={"username": "alice", "password": "secret1"}
        ).status_code == 200
        assert client.post(
            "/api/users/login", json={"username": "alice", "password": "secret1"}
        ).status_code == 200
        yield client, application, judge_root


def add_problem(
    client: TestClient,
    problem_id: str,
    testcases: list[dict[str, str]],
    *,
    time_limit: float = 1.0,
    memory_limit: int = 128,
) -> None:
    payload = {
        "id": problem_id,
        "title": problem_id,
        "description": "Judge integration fixture.",
        "input_description": "Input.",
        "output_description": "Output.",
        "samples": [testcases[0]],
        "constraints": "Controlled test only.",
        "testcases": testcases,
        "time_limit": time_limit,
        "memory_limit": memory_limit,
    }
    assert client.post("/api/problems/", json=payload).status_code == 200


def judge(client: TestClient, application: FastAPI, **request: Any) -> JudgeResult:
    assert client.portal is not None
    return client.portal.call(application.state.judge_service.judge, JudgeRequest(**request))


def assert_clean(root: Path) -> None:
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_python_ac_multiple_cases_and_full_score(
    judge_context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, application, root = judge_context
    add_problem(
        client,
        "py_ac",
        [{"input": "1 2", "output": "3"}, {"input": "-2 5", "output": "3"}],
    )

    result = judge(
        client,
        application,
        problem_id="py_ac",
        language="python",
        code="a, b = map(int, input().split())\nprint(a + b)",
    )

    assert result.status is Status.AC
    assert result.score == 20
    assert [item.result for item in result.testcase_results] == [
        Status.AC,
        Status.AC,
    ]
    assert_clean(root)


def test_python_wa_and_partial_score(
    judge_context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, application, _ = judge_context
    add_problem(
        client,
        "py_partial",
        [{"input": "1", "output": "1"}, {"input": "2", "output": "999"}],
    )

    result = judge(
        client,
        application,
        problem_id="py_partial",
        language="python",
        code="print(input())",
    )

    assert result.status is Status.WA
    assert result.score == 10
    assert [item.result for item in result.testcase_results] == [
        Status.AC,
        Status.WA,
    ]


def test_python_runtime_error(judge_context: tuple[TestClient, FastAPI, Path]) -> None:
    client, application, _ = judge_context
    add_problem(client, "py_re", [{"input": "", "output": ""}])

    result = judge(
        client,
        application,
        problem_id="py_re",
        language="python",
        code="raise RuntimeError('controlled failure')",
    )

    assert result.status is Status.RE
    assert result.testcase_results[0].error_summary
    assert "oj-judge-" not in result.testcase_results[0].error_summary


def test_python_time_limit_uses_problem_limit(
    judge_context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, application, _ = judge_context
    add_problem(
        client,
        "py_tle",
        [{"input": "", "output": ""}],
        time_limit=0.15,
    )

    result = judge(
        client,
        application,
        problem_id="py_tle",
        language="python",
        code="while True:\n    pass",
    )

    assert result.status is Status.TLE
    assert result.time < 1.0


def test_python_memory_limit(judge_context: tuple[TestClient, FastAPI, Path]) -> None:
    client, application, _ = judge_context
    add_problem(
        client,
        "py_mle",
        [{"input": "", "output": ""}],
        time_limit=3,
        memory_limit=64,
    )

    result = judge(
        client,
        application,
        problem_id="py_mle",
        language="python",
        code="items = []\nwhile True:\n    items.append(bytearray(1024 * 1024))",
    )

    assert result.status is Status.MLE


@pytest.mark.parametrize(
    ("code", "expected", "summary"),
    [
        ("import sys\nsys.stdout.buffer.write(b'\\xff')", Status.UNK, "UTF-8"),
        ("print('x' * 100000)", Status.WA, "capture limit"),
        ("while True:\n print('x' * 1000, flush=True)", Status.TLE, "time limit"),
    ],
)
def test_invalid_and_unbounded_output_is_safe(
    judge_context: tuple[TestClient, FastAPI, Path],
    code: str,
    expected: Status,
    summary: str,
) -> None:
    client, application, _ = judge_context
    add_problem(
        client,
        f"output_{expected.value.lower()}",
        [{"input": "", "output": "x"}],
        time_limit=0.2,
    )

    result = judge(
        client,
        application,
        problem_id=f"output_{expected.value.lower()}",
        language="python",
        code=code,
    )

    assert result.status is expected
    assert summary in result.testcase_results[0].error_summary
    assert len(result.stdout.encode("utf-8")) <= 4096


def test_timed_out_child_process_is_terminated(
    judge_context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, application, _ = judge_context
    add_problem(client, "child_cleanup", [{"input": "", "output": ""}], time_limit=0.25)
    code = (
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print(child.pid, flush=True)\n"
        "while True:\n    pass"
    )

    result = judge(
        client,
        application,
        problem_id="child_cleanup",
        language="python",
        code=code,
    )

    assert result.status is Status.TLE
    child_pid = int(result.stdout.strip())
    deadline = time.monotonic() + 2
    while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not psutil.pid_exists(child_pid)


def test_stderr_capture_is_truncated(
    judge_context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, application, _ = judge_context
    add_problem(client, "stderr_limit", [{"input": "", "output": ""}])

    result = judge(
        client,
        application,
        problem_id="stderr_limit",
        language="python",
        code="import sys\nsys.stderr.write('e' * 100000)\nraise SystemExit(1)",
    )

    assert result.status is Status.RE
    assert result.testcase_results[0].error_summary == "stderr exceeded capture limit"
    assert len(result.stderr.encode("utf-8")) <= 4096


def test_executor_exception_becomes_unknown_result(
    judge_context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, application, _ = judge_context
    add_problem(client, "unknown", [{"input": "", "output": ""}])

    class BrokenExecutor:
        async def execute(self, *_: Any, **__: Any) -> None:
            raise RuntimeError("controlled executor failure")

    application.state.judge_service.executor = BrokenExecutor()
    result = judge(
        client,
        application,
        problem_id="unknown",
        language="python",
        code="print('unreachable')",
    )

    assert result.status is Status.UNK
    assert result.testcase_results[0].result is Status.UNK
    assert "controlled executor failure" in result.testcase_results[0].error_summary


def test_user_process_does_not_receive_application_secrets(
    judge_context: tuple[TestClient, FastAPI, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, application, _ = judge_context
    monkeypatch.setenv("OJ_MODEL_API_KEY", "must-not-leak")
    add_problem(client, "safe_env", [{"input": "", "output": "missing"}])

    result = judge(
        client,
        application,
        problem_id="safe_env",
        language="python",
        code="import os\nprint(os.getenv('OJ_MODEL_API_KEY', 'missing'))",
    )

    assert result.status is Status.AC
    assert "must-not-leak" not in result.stdout


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is not installed")
@pytest.mark.parametrize(
    ("problem_id", "code", "expected", "time_limit"),
    [
        (
            "cpp_ac",
            "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b;}",
            Status.AC,
            3.0,
        ),
        ("cpp_ce", "int main( {", Status.CE, 3.0),
        (
            "cpp_re",
            "int main(){return 7;}",
            Status.RE,
            3.0,
        ),
        ("cpp_tle", "int main(){while(true){} }", Status.TLE, 0.3),
    ],
)
def test_cpp_result_states(
    judge_context: tuple[TestClient, FastAPI, Path],
    problem_id: str,
    code: str,
    expected: Status,
    time_limit: float,
) -> None:
    client, application, root = judge_context
    add_problem(
        client,
        problem_id,
        [{"input": "1 2", "output": "3"}, {"input": "3 4", "output": "7"}],
        time_limit=time_limit,
    )

    result = judge(
        client,
        application,
        problem_id=problem_id,
        language="cpp",
        code=code,
    )

    assert result.status is expected
    if expected is Status.AC:
        assert result.score == 20
    if expected is Status.CE:
        assert result.score == 0
        assert result.testcase_results == []
        assert result.compile_info not in (None, "success")
    assert_clean(root)
