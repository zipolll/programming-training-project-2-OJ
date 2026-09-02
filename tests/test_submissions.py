"""Submission lifecycle, API contract, permissions, recovery, and concurrency tests."""

import asyncio
import inspect
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.judge.models import JudgeResult
from backend.app.modules.judge.models import TestcaseResult as CaseResult
from backend.app.modules.judge.models import TestcaseStatus as Status
from backend.app.modules.submissions.router import router as submissions_router


def problem_payload(problem_id: str = "P1001", testcases: int = 2) -> dict[str, Any]:
    return {
        "id": problem_id,
        "title": "A+B",
        "description": "Add two integers.",
        "input_description": "Two integers.",
        "output_description": "Their sum.",
        "samples": [{"input": "1 2", "output": "3"}],
        "constraints": "integers",
        "testcases": [{"input": f"{i} 1", "output": str(i + 1)} for i in range(testcases)],
    }


def result(status: Status = Status.AC, testcase_count: int = 2) -> JudgeResult:
    details = [] if status is Status.CE else [
        CaseResult(id=index, result=status, time=0.01, memory=2.0)
        for index in range(1, testcase_count + 1)
    ]
    return JudgeResult(
        status=status,
        score=sum(item.result is Status.AC for item in details) * 10,
        compile_info="compiler error" if status is Status.CE else None,
        stdout="captured output",
        stderr="runtime diagnostics" if status is Status.RE else "",
        time=0.02,
        memory=2.0,
        testcase_results=details,
    )


class FakeJudge:
    def __init__(self, outcomes: list[JudgeResult | Exception] | None = None) -> None:
        self.outcomes = outcomes or [result()]
        self.calls = 0

    async def judge(self, request: object) -> JudgeResult:
        del request
        await asyncio.sleep(0.01)
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def submission_context(tmp_path: Path) -> Iterator[tuple[TestClient, FastAPI, FakeJudge]]:
    settings = Settings(
        database_path=tmp_path / "oj.sqlite3",
        problems_path=tmp_path / "problems",
        environment="test",
        submission_rate_limit_per_minute=100,
        submission_code_limit=1024,
        evaluation_shutdown_timeout_seconds=0.2,
    )
    application = create_app(settings)
    with TestClient(application) as client:
        fake = FakeJudge()
        application.state.judge_service = fake
        register_login(client, "alice")
        assert client.post("/api/problems/", json=problem_payload()).status_code == 200
        yield client, application, fake


def register_login(client: TestClient, username: str) -> int:
    response = client.post(
        "/api/users/register", json={"username": username, "password": "secret1"}
    )
    user_id = int(response.json()["data"]["id"]) if response.status_code == 200 else -1
    assert client.post(
        "/api/users/login", json={"username": username, "password": "secret1"}
    ).status_code == 200
    return user_id


def login_admin(client: TestClient) -> None:
    assert client.post(
        "/api/users/login",
        json={"username": "admin", "password": "admintestpassword"},
    ).status_code == 200


def submit(client: TestClient, problem_id: str = "P1001", code: str = "print(1)") -> Any:
    return client.post(
        "/api/submissions/",
        json={"problem_id": problem_id, "language": "python", "code": code},
    )


def wait_for_status(client: TestClient, submission_id: str, expected: str) -> dict[str, Any]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/submissions/{submission_id}")
        if response.status_code == 200 and response.json()["data"]["status"] == expected:
            return response.json()["data"]
        time.sleep(0.01)
    raise AssertionError(f"submission {submission_id} did not become {expected}")


def test_submit_returns_pending_then_worker_succeeds_and_persists_details(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, application, _ = submission_context

    response = submit(client)

    assert response.json()["data"]["status"] == "pending"
    submission_id = response.json()["data"]["submission_id"]
    detail = wait_for_status(client, submission_id, "success")
    assert detail == {
        "submission_id": submission_id,
        "status": "success",
        "score": 20,
        "counts": 20,
        "compile_info": None,
        "run_info": {"result": "finished", "message": "2 test cases finished"},
        "error_info": "",
    }
    with sqlite3.connect(application.state.settings.database_path) as connection:
        rows = connection.execute(
            "SELECT testcase_id, result, time, memory FROM submission_testcases"
        ).fetchall()
    assert rows == [(1, "AC", 0.01, 2.0), (2, "AC", 0.01, 2.0)]
    assert "details" not in detail
    assert "code" not in detail


@pytest.mark.parametrize(
    "judge_status",
    [
        Status.AC,
        Status.WA,
        Status.CE,
        Status.RE,
        Status.TLE,
        Status.MLE,
        Status.UNK,
    ],
)
def test_all_judge_results_are_successful_evaluations(
    submission_context: tuple[TestClient, FastAPI, FakeJudge], judge_status: Status
) -> None:
    client, application, _ = submission_context
    application.state.judge_service = FakeJudge([result(judge_status)])

    submission_id = submit(client).json()["data"]["submission_id"]

    assert wait_for_status(client, submission_id, "success")["status"] == "success"


def test_judge_exception_becomes_error_and_worker_continues(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, application, _ = submission_context
    application.state.judge_service = FakeJudge([RuntimeError("boom"), result()])

    first = submit(client).json()["data"]["submission_id"]
    second = submit(client).json()["data"]["submission_id"]

    failed = wait_for_status(client, first, "error")
    assert failed["error_info"] == "evaluation task failed"
    assert wait_for_status(client, second, "success")["score"] == 20


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"problem_id": "missing", "language": "python", "code": "x"}, 404),
        ({"problem_id": "P1001", "language": "missing", "code": "x"}, 404),
        ({"problem_id": "P1001", "language": "python", "code": ""}, 400),
        ({"problem_id": "P1001", "language": "python", "code": "x" * 1025}, 400),
        ({"problem_id": "P1001", "language": "python"}, 400),
    ],
)
def test_submission_validation(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
    payload: dict[str, object],
    expected: int,
) -> None:
    client, _, _ = submission_context
    assert client.post("/api/submissions/", json=payload).status_code == expected


def test_disabled_language_is_not_accepted(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, application, _ = submission_context
    with sqlite3.connect(application.state.settings.database_path) as connection:
        connection.execute("UPDATE languages SET enabled = 0 WHERE name = 'python'")
        connection.commit()

    assert submit(client).status_code == 404


def test_submission_requires_login(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "db.sqlite3", problems_path=tmp_path / "p")
    with TestClient(create_app(settings)) as client:
        assert submit(client).status_code == 401


def test_rate_limit_is_course_compatible(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        problems_path=tmp_path / "p",
        submission_rate_limit_per_minute=3,
    )
    application = create_app(settings)
    with TestClient(application) as client:
        application.state.judge_service = FakeJudge()
        register_login(client, "alice")
        client.post("/api/problems/", json=problem_payload())
        assert [submit(client).status_code for _ in range(3)] == [200, 200, 200]
        assert submit(client).status_code == 429


def test_list_requires_primary_filter_and_valid_pagination(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, _, _ = submission_context
    assert client.get("/api/submissions/").status_code == 400
    assert client.get("/api/submissions/?problem_id=P1001&page=1").status_code == 400
    for query in ("page=0&page_size=1", "page=1&page_size=0", "status=invalid"):
        assert client.get(f"/api/submissions/?problem_id=P1001&{query}").status_code == 400


def test_list_pagination_filters_stable_order_and_visibility(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, _, _ = submission_context
    alice_id = int(client.get("/api/users/me").json()["data"]["id"])
    alice_submissions = [submit(client).json()["data"]["submission_id"] for _ in range(4)]
    for submission_id in alice_submissions:
        wait_for_status(client, submission_id, "success")
    bob_id = register_login(client, "bobby")
    bob_submissions = [submit(client).json()["data"]["submission_id"] for _ in range(2)]
    for submission_id in bob_submissions:
        wait_for_status(client, submission_id, "success")

    own = client.get("/api/submissions/?problem_id=P1001&page_size=1")
    assert own.json()["data"]["total"] == 2
    assert own.json()["data"]["submissions"][0]["submission_id"] == bob_submissions[-1]
    assert client.get(f"/api/submissions/?user_id={alice_id}").status_code == 403
    combined = client.get(
        f"/api/submissions/?user_id={bob_id}&problem_id=P1001&status=success&page=2&page_size=1"
    )
    assert combined.json()["data"]["submissions"][0]["submission_id"] == bob_submissions[0]
    assert client.get(
        f"/api/submissions/?user_id={bob_id}&page=9&page_size=1"
    ).json()["data"]["submissions"] == []

    login_admin(client)
    all_for_problem = client.get("/api/submissions/?problem_id=P1001")
    ids = [item["submission_id"] for item in all_for_problem.json()["data"]["submissions"]]
    assert all_for_problem.json()["data"]["total"] == 6
    assert ids == sorted(ids, key=int, reverse=True)
    allowed_fields = {"submission_id", "status", "score", "counts"}
    assert all(
        set(item) <= allowed_fields
        for item in all_for_problem.json()["data"]["submissions"]
    )


def test_detail_permissions_and_missing(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, _, _ = submission_context
    submission_id = submit(client).json()["data"]["submission_id"]
    wait_for_status(client, submission_id, "success")
    register_login(client, "bobby")
    assert client.get(f"/api/submissions/{submission_id}").status_code == 403
    login_admin(client)
    assert client.get(f"/api/submissions/{submission_id}").status_code == 200
    assert client.get("/api/submissions/999999").status_code == 404


def test_rejudge_requires_admin_and_returns_pending(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, _, _ = submission_context
    submission_id = submit(client).json()["data"]["submission_id"]
    wait_for_status(client, submission_id, "success")
    assert client.put(f"/api/submissions/{submission_id}/rejudge").status_code == 403
    login_admin(client)
    response = client.put(f"/api/submissions/{submission_id}/rejudge")
    assert response.json() == {
        "code": 200,
        "msg": "rejudge started",
        "data": {"submission_id": submission_id, "status": "pending"},
    }
    assert client.put("/api/submissions/999999/rejudge").status_code == 404


def test_rejudge_versions_prevent_old_result_overwrite(
    submission_context: tuple[TestClient, FastAPI, FakeJudge],
) -> None:
    client, application, _ = submission_context
    entered = threading.Event()
    release = threading.Event()

    class VersionedJudge:
        calls = 0

        async def judge(self, request: object) -> JudgeResult:
            del request
            self.calls += 1
            if self.calls == 1:
                entered.set()
                await asyncio.to_thread(release.wait)
                return result(Status.WA)
            return result(Status.AC)

    judge = VersionedJudge()
    application.state.judge_service = judge
    submission_id = submit(client).json()["data"]["submission_id"]
    assert entered.wait(timeout=1)
    login_admin(client)
    assert client.put(f"/api/submissions/{submission_id}/rejudge").status_code == 200
    assert client.put(f"/api/submissions/{submission_id}/rejudge").status_code == 200
    release.set()

    detail = wait_for_status(client, submission_id, "success")
    assert detail["score"] == 20
    stored = client.app.state.submission_repository
    submission = asyncio.run(stored.get(int(submission_id)))
    assert submission is not None
    assert submission.evaluation_version == 3
    assert submission.result is Status.AC
    assert judge.calls == 2


def test_submission_survives_restart_and_pending_is_recovered(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "persistent.sqlite3",
        problems_path=tmp_path / "problems",
        submission_rate_limit_per_minute=100,
    )
    first_app = create_app(settings)
    with TestClient(first_app) as client:
        register_login(client, "alice")
        client.post("/api/problems/", json=problem_payload(testcases=1))
        user_id = int(client.get("/api/users/me").json()["data"]["id"])
    now = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(settings.database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO submissions
                (user_id, problem_id, language, code, status, counts,
                 created_at, updated_at, evaluation_version)
            VALUES (?, 'P1001', 'python', 'a,b=map(int,input().split());print(a+b)',
                    'pending', 10, ?, ?, 1)
            """,
            (user_id, now, now),
        )
        submission_id = str(cursor.lastrowid)
        connection.commit()

    second_app = create_app(settings)
    with TestClient(second_app) as client:
        assert client.post(
            "/api/users/login", json={"username": "alice", "password": "secret1"}
        ).status_code == 200
        assert wait_for_status(client, submission_id, "success")["score"] == 10
        manager = second_app.state.evaluation_task_manager
    assert manager._worker is None
    assert not manager.tracked


def test_submission_route_handlers_are_async() -> None:
    endpoints = [
        route.endpoint for route in submissions_router.routes if hasattr(route, "endpoint")
    ]
    assert len(endpoints) == 4
    assert all(inspect.iscoroutinefunction(endpoint) for endpoint in endpoints)
