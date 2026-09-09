"""Course API clarifications: privacy, reset, error precedence, and resource inheritance."""

import asyncio
import json
import sys
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.agent.models import AgentStatus, AuthoringRequest
from backend.app.modules.judge.executor import ProcessOutcome
from backend.app.modules.judge.models import JudgeRequest, JudgeResult
from backend.app.modules.judge.models import TestcaseResult as CaseResult
from backend.app.modules.judge.models import TestcaseStatus as Verdict
from backend.app.modules.submissions.models import SubmissionRequest
from backend.app.modules.submissions.service import SubmissionRateLimitError


def problem(pid="P1", **extra):
    return {
        "id": pid, "title": "sum", "description": "sum", "input_description": "numbers",
        "output_description": "sum", "constraints": "small",
        "samples": [{"input": "1 2", "output": "3"}],
        "testcases": [{"input": "1 2", "output": "3"}], **extra,
    }


def result(verdict=Verdict.AC):
    return JudgeResult(
        status=verdict, score=10 if verdict is Verdict.AC else 0, time=0.01, memory=2.0,
        testcase_results=[CaseResult(
            id=1, result=verdict, time=0.01, memory=2.0, error_summary="private source fragment",
        )],
    )


def login(client, username="admin"):
    response = client.post("/api/auth/login", json={
        "username": username, "password": "admintestpassword" if username == "admin" else "secret1",
    })
    assert response.status_code == 200
    return int(response.json()["data"]["user_id"])


def register(client, username):
    response = client.post("/api/users/", json={"username": username, "password": "secret1"})
    assert response.status_code == 200
    return int(response.json()["data"]["user_id"])


@pytest.fixture
def context(tmp_path):
    settings = Settings(
        _env_file=None, database_path=tmp_path / "test.db", problems_path=tmp_path / "problems",
        environment="test", evaluation_shutdown_timeout_seconds=0.05,
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        login(client)
        assert client.post("/api/problems/", json=problem()).status_code == 200
        yield client, app, settings


def seed_submission(client, app, uid, pid="P1", verdict=Verdict.AC):
    async def seed():
        repository = app.state.submission_repository
        submission = await repository.create(
            user_id=uid, problem_id=pid, language="python", code="private source",
            counts=10, now=datetime.now(timezone.utc),
        )
        if verdict is not None:
            await repository.complete_if_current(
                submission.submission_id, 1, result(verdict), datetime.now(timezone.utc),
            )
        return submission.submission_id

    return client.portal.call(seed)


def test_log_visibility_matrix_and_submission_privacy(context):
    client, app, _ = context
    alice = register(client, "alice")
    register(client, "bobby")
    sid = seed_submission(client, app, alice)
    for public in (False, True, False):
        login(client)
        response = client.put("/api/problems/P1/log_visibility", json={"public_cases": public})
        assert response.json()["data"] == {"problem_id": "P1", "public_cases": public}
        admin = client.get(f"/api/submissions/{sid}/log").json()["data"]
        assert admin["details"][0]["result"] == "AC"
        login(client, "alice")
        own = client.get(f"/api/submissions/{sid}/log").json()["data"]
        assert own["score"] == own["counts"] == 10
        assert ("details" in own) is public
        assert client.get(f"/api/submissions/{sid}").status_code == 200
        login(client, "bobby")
        other = client.get(f"/api/submissions/{sid}/log")
        assert other.status_code == (200 if public else 403)
        if public:
            data = other.json()["data"]
            assert set(data) == {"details", "score", "counts"}
            assert set(data["details"][0]) == {"id", "result", "time", "memory"}
            assert "private source" not in other.text
        assert client.get(f"/api/submissions/{sid}").status_code == 403
    client.cookies.clear()
    assert client.get(f"/api/submissions/{sid}/log").status_code == 401
    login(client)
    audit = client.get("/api/logs/access/?problem_id=P1").json()["data"]
    assert {entry["action"] for entry in audit} == {"view_logs"}
    assert {entry["status"] for entry in audit} == {"200", "403"}


def test_visibility_defaults_validation_permissions_and_persistence(context):
    client, app, settings = context
    alice = register(client, "alice")
    sid = seed_submission(client, app, alice)
    login(client, "alice")
    assert client.get(f"/api/submissions/{sid}/log").json()["data"] == {
        "score": 10, "counts": 10,
    }
    assert client.put("/api/problems/P1/log_visibility", json={}).status_code == 403
    assert client.get("/api/problems/P1/log_visibility").status_code == 403
    login(client)
    assert client.get("/api/problems/P1/log_visibility").json()["data"] == {
        "problem_id": "P1", "public_cases": False,
    }
    for value in ("true", 1, None):
        assert client.put(
            "/api/problems/P1/log_visibility", json={"public_cases": value},
        ).status_code == 400
    assert client.put("/api/problems/missing/log_visibility", json={}).status_code == 404
    assert client.get("/api/problems/missing/log_visibility").status_code == 404
    client.put("/api/problems/P1/log_visibility", json={"public_cases": True})
    assert client.get("/api/problems/P1/log_visibility").json()["data"] == {
        "problem_id": "P1", "public_cases": True,
    }
    with TestClient(create_app(settings)) as restarted:
        login(restarted, "alice")
        assert "details" in restarted.get(f"/api/submissions/{sid}/log").json()["data"]
    cleared = client.put("/api/problems/P1/log_visibility", json={}).json()["data"]
    assert cleared["public_cases"] is False
    assert client.get("/api/problems/P1/log_visibility").json()["data"] == {
        "problem_id": "P1", "public_cases": False,
    }


def test_deleted_problem_rolls_back_counts_without_reviving_old_submissions(context):
    client, app, _ = context
    alice = register(client, "alice")
    bob = register(client, "bobby")
    client.post("/api/problems/", json=problem("P2"))
    for verdict in (Verdict.AC, Verdict.AC, Verdict.WA, None):
        seed_submission(client, app, alice, verdict=verdict)
    seed_submission(client, app, alice, pid="P2")
    seed_submission(client, app, bob)
    seed_submission(client, app, bob, pid="P2", verdict=Verdict.WA)
    before = client.get(f"/api/users/{alice}").json()["data"]
    assert (before["submit_count"], before["resolve_count"]) == (5, 2)
    assert client.delete("/api/problems/P1").status_code == 200
    for uid, expected in ((alice, (1, 1)), (bob, (1, 0))):
        user = client.get(f"/api/users/{uid}").json()["data"]
        assert (user["submit_count"], user["resolve_count"]) == expected
        listed = next(u for u in client.get("/api/users/").json()["data"]["users"]
                      if int(u["user_id"]) == uid)
        assert (listed["submit_count"], listed["resolve_count"]) == expected
    # Historical records remain readable; recreating an ID cannot restore old contributions.
    assert client.get(f"/api/submissions/?user_id={alice}").json()["data"]["total"] == 5
    client.post("/api/problems/", json=problem())
    assert client.get(f"/api/users/{alice}").json()["data"]["submit_count"] == 1
    seed_submission(client, app, alice)
    assert client.get(f"/api/users/{alice}").json()["data"]["resolve_count"] == 2


@pytest.mark.parametrize("endpoint", ["/api/submissions/", "/api/logs/access/"])
def test_list_primary_filters_and_pagination(context, endpoint):
    client, _, _ = context
    for params in ({}, {"page_size": 1}, {"user_id": ""}, {"problem_id": ""},
                   {"user_id": 1, "page": 1}, {"problem_id": "P1", "page_size": 0}):
        assert client.get(endpoint, params=params).status_code == 400
    for params in ({"user_id": 1}, {"problem_id": "P1"},
                   {"problem_id": "P1", "page_size": 1},
                   {"user_id": 1, "problem_id": "P1", "page": 1, "page_size": 2}):
        assert client.get(endpoint, params=params).status_code == 200


def test_error_precedence_and_json_envelopes(context):
    client, app, _ = context
    client.cookies.clear()
    for endpoint in ("/api/submissions/", "/api/users/admin", "/api/agent/tasks"):
        assert client.post(endpoint, content="{", headers={
            "Content-Type": "application/json",
        }).status_code == 401
    uid = register(client, "alice")
    login(client, "alice")
    assert client.post("/api/users/admin", content="{", headers={
        "Content-Type": "application/json",
    }).status_code == 403
    assert client.get("/api/submissions/?user_id=1&page=bad").status_code == 403
    for _ in range(3):
        seed_submission(client, app, uid)
    body = {"problem_id": "missing", "language": "missing", "code": "print(3)"}
    assert client.post("/api/submissions/", json=body).status_code == 429
    assert client.post("/api/submissions/", json={**body, "code": ""}).status_code == 400
    assert client.get("/api/not-a-route").json()["code"] == 404
    assert client.delete("/api/languages/").json()["code"] == 405

    async def broken():
        raise RuntimeError("private server path and key")

    app.state.language_service.list_enabled_names = broken
    error = client.get("/api/languages/")
    assert error.status_code == error.json()["code"] == 500
    assert "private" not in error.text


@pytest.mark.parametrize("overrides,language,expected", [
    ({}, {}, (3.0, 128)),
    ({}, {"time_limit": 0.7, "memory_limit": 80}, (0.7, 80)),
    ({"time_limit": 2.0}, {"time_limit": 0.7, "memory_limit": 80}, (2.0, 80)),
    ({"memory_limit": 64}, {"time_limit": 0.7}, (0.7, 64)),
    ({"time_limit": 3.0, "memory_limit": 128},
     {"time_limit": 0.7, "memory_limit": 80}, (3.0, 128)),
])
def test_resource_priority_survives_storage_and_restart(context, overrides, language, expected):
    client, _, settings = context
    client.put("/api/problems/P1", json=problem(**overrides))
    registration = {"name": "custom", "file_ext": ".py", "run_cmd": "python3 {src}", **language}
    assert client.post("/api/languages/", json=registration).status_code == 200
    stored = json.loads((settings.problems_path / "P1.json").read_text())
    for key in ("time_limit", "memory_limit"):
        assert (key in stored) == (key in overrides)
    restarted = create_app(settings)
    with TestClient(restarted) as second:
        calls = []

        class CaptureExecutor:
            async def execute(self, arguments, **kwargs):
                calls.append((kwargs["time_limit"], kwargs["memory_limit_mb"]))
                assert arguments[-1].endswith("main.py")
                return ProcessOutcome(None, 0, b"3", b"", 0.01, 1.0)

        restarted.state.judge_service.executor = CaptureExecutor()
        judged = second.portal.call(restarted.state.judge_service.judge, JudgeRequest(
            problem_id="P1", language="custom", code="print(3)",
        ))
        assert judged.status is Verdict.AC
        assert calls == [expected]


def test_reset_cancels_running_work_and_recreates_initial_state(context):
    client, app, settings = context
    alice = register(client, "alice")
    login(client, "alice")
    assert client.post("/api/reset/").status_code == 403
    entered = threading.Event()
    cancelled = threading.Event()

    class BlockedJudge:
        async def judge(self, request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    app.state.judge_service = BlockedJudge()
    assert client.post("/api/submissions/", json={
        "problem_id": "P1", "language": "python", "code": "print(3)",
    }).status_code == 200
    assert entered.wait(2)
    client.post("/api/problem-banks/", json={"name": "bank", "problem_ids": ["P1"]})
    client.post("/api/languages/", json={"name": "custom", "file_ext": ".py",
                                         "run_cmd": "python3 {src}"})
    login(client)
    cookie = client.cookies.get("session_id")
    response = client.post("/api/reset/")
    assert response.json() == {"code": 200, "msg": "system reset successfully", "data": None}
    assert cancelled.is_set()
    assert not list(settings.problems_path.glob("*.json"))
    assert client.get("/api/users/").status_code == 401
    client.cookies.set("session_id", cookie)
    assert client.get("/api/users/").status_code == 401
    client.cookies.clear()
    login(client)
    users = client.get("/api/users/").json()["data"]
    assert users["total"] == 1 and users["users"][0]["username"] == "admin"
    assert client.get(f"/api/submissions/?user_id={alice}").json()["data"]["total"] == 0
    assert client.get("/api/languages/").json()["data"] == {"name": ["python", "cpp"]}
    assert client.get("/api/logs/access/?user_id=1").json()["data"] == []
    assert client.post("/api/reset/").status_code == 200  # Repeatability and worker restart.


def test_ai_administrator_access_and_finished_cancel(context):
    client, app, _ = context
    alice = register(client, "alice")
    register(client, "bobby")

    async def seed():
        await app.state.agent_repository.create_task("task", alice, AuthoringRequest(
            required_knowledge=["sum"], difficulty="easy", problem_type="coding",
        ), currency="USD")
        await app.state.agent_repository.update_task("task", status=AgentStatus.SUCCESS)

    client.portal.call(seed)
    assert client.get("/api/agent/tasks/task").status_code == 200
    assert client.get("/api/agent/tasks/task/events").status_code == 200
    assert client.post("/api/agent/tasks/task/cancel").status_code == 409
    login(client, "bobby")
    assert client.get("/api/agent/tasks/task").status_code == 403
    assert client.post("/api/agent/tasks/task/cancel").status_code == 403
    login(client, "alice")
    assert client.post("/api/agent/tasks/task/cancel").status_code == 409
    assert client.post("/api/agent/tasks", json={
        "required_knowledge": ["sum"], "difficulty": "easy", "problem_type": "coding",
        "existing_problem_id": "missing",
    }).status_code == 404


def test_builtin_python_path_migration_preserves_language_limits(context):
    client, app, _ = context

    async def migrate():
        async with app.state.database.connect() as connection:
            await connection.execute(
                "UPDATE languages SET run_args=?, time_limit=0.9 WHERE name='python'",
                (json.dumps(["C:/old/windows/python.exe", "{src}"]),),
            )
            await connection.commit()
        await app.state.language_service.initialize()
        return await app.state.language_service.get_enabled("python")

    language = client.portal.call(migrate)
    assert language.run_args == (sys.executable, "{src}")
    assert language.time_limit == 0.9


def test_concurrent_submissions_cannot_bypass_rate_limit(context):
    client, app, _ = context
    register(client, "alice")

    async def submit_together():
        user = await app.state.auth_service.users.get_by_username("alice")
        request = SubmissionRequest(problem_id="P1", language="python", code="print(3)")
        return await asyncio.gather(
            *(app.state.submission_service.create(user, request) for _ in range(8)),
            return_exceptions=True,
        )

    results = client.portal.call(submit_together)
    assert sum(isinstance(item, SubmissionRateLimitError) for item in results) == 5
    assert sum(not isinstance(item, Exception) for item in results) == 3


def test_deletion_waits_for_inflight_submission_before_excluding_statistics(context):
    client, app, _ = context
    uid = register(client, "alice")

    async def race():
        entered, release = asyncio.Event(), asyncio.Event()
        original = app.state.submission_repository.create

        async def paused_create(**kwargs):
            entered.set()
            await release.wait()
            return await original(**kwargs)

        app.state.submission_repository.create = paused_create
        user = await app.state.auth_service.users.get_by_username("alice")
        submit = asyncio.create_task(app.state.submission_service.create(
            user, SubmissionRequest(problem_id="P1", language="python", code="print(3)"),
        ))
        await entered.wait()
        delete = asyncio.create_task(app.state.problem_service.delete_problem("P1"))
        await asyncio.sleep(0)
        assert not delete.done()
        release.set()
        await asyncio.gather(submit, delete)

    client.portal.call(race)
    data = client.get(f"/api/users/{uid}").json()["data"]
    assert data["submit_count"] == data["resolve_count"] == 0
