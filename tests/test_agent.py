"""Advance AI authoring security, lifecycle, usage, cancellation, and import tests."""

import asyncio
import json
import sqlite3
import time
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.agent.models import (
    AgentConfigUpdate,
    AuthoringRequest,
    GeneratedProblem,
    validate_provider_url,
)
from backend.app.modules.agent.task_manager import apply_requested_metadata

FAKE_KEY = "test-provider-key-never-real"


def generated_problem() -> dict[str, Any]:
    return {
        "problem": {
            "id": "AI_SUM_1",
            "title": "整数求和",
            "description": "求一行整数之和。",
            "input_description": "一行整数。",
            "output_description": "输出整数和。",
            "samples": [{"input": "1 2\n", "output": "3\n"}],
            "constraints": "整数个数至少为 1。",
            "testcases": [
                {"input": "1 2\n", "output": "3\n"},
                {"input": "0\n", "output": "0\n"},
                {"input": "-1 1\n", "output": "0\n"},
                {"input": ("1 " * 600) + "\n", "output": "600\n"},
            ],
            "hint": "",
            "source": "AI draft",
            "tags": ["sum"],
            "time_limit": 2.0,
            "memory_limit": 128,
            "author": "AI",
            "difficulty": "入门",
        },
        "solution_explanation": "Read and sum every integer.",
        "complexity_analysis": "O(n) time and O(n) input storage.",
        "reference_solution_language": "python",
        "reference_solution": "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
        "wrong_solutions": ["print(0)\n"],
    }


@pytest.fixture
def agent_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path, list[httpx.Request]]]:
    database = tmp_path / "oj.sqlite3"
    settings = Settings(
        database_path=database,
        problems_path=tmp_path / "problems",
        environment="test",
        credential_encryption_key=Fernet.generate_key().decode(),
    )
    application = create_app(settings)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(generated_problem())}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        )

    with TestClient(application) as client:
        application.state.agent_model_client.transport = httpx.MockTransport(handler)
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "admintestpassword"}
            ).status_code
            == 200
        )
        yield client, database, requests


def config_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "provider_url": "https://model.example/v1",
        "model_name": "test-model",
        "api_key": FAKE_KEY,
        "input_price_per_million_tokens": "2.5",
        "output_price_per_million_tokens": "10",
        "currency": "USD",
        "request_timeout": 10.0,
        "max_iterations": 3,
        "max_output_tokens": 4096,
    }
    payload.update(updates)
    return payload


def test_agent_config_defaults_allow_large_structured_problem_output() -> None:
    config = AgentConfigUpdate(
        provider_url="https://model.example/v1",
        model_name="test-model",
    )
    assert config.request_timeout == 180.0
    assert config.max_output_tokens == 50000


def authoring_payload() -> dict[str, Any]:
    return {
        "required_knowledge": ["sum"],
        "difficulty": "入门",
        "problem_type": "algorithm",
        "expected_algorithm": "O(n)",
        "forbidden_knowledge": [],
        "data_scale": "n <= 600",
        "time_limit": 2.0,
        "memory_limit": 128,
        "background_preference": "",
        "testcase_count": 4,
        "additional_requirements": "deterministic",
        "adapt_existing": False,
        "existing_problem_id": None,
    }


@pytest.mark.parametrize("problem_type", ["数学", "自定义专题题"])
def test_minimal_authoring_request_allows_ai_selected_advanced_fields(
    problem_type: str,
) -> None:
    request = AuthoringRequest.model_validate(
        {
            "required_knowledge": ["前缀和"],
            "difficulty": "中等",
            "problem_type": problem_type,
        }
    )

    assert request.problem_type == problem_type
    assert request.expected_algorithm == ""
    assert request.data_scale == ""
    assert request.time_limit == 2.0
    assert request.memory_limit == 128
    assert request.testcase_count == 10


def test_partial_authoring_settings_allow_ai_selected_knowledge() -> None:
    request = AuthoringRequest.model_validate({"difficulty": "中等"})
    assert request.required_knowledge == []
    assert request.model_dump(exclude_unset=True) == {"difficulty": "中等"}


@pytest.mark.parametrize("payload", [{}, {"prompt": "  "}, {"required_knowledge": []}])
def test_empty_authoring_request_is_rejected(payload: dict) -> None:
    with pytest.raises(ValueError):
        AuthoringRequest.model_validate(payload)


def _new_success(client: TestClient, payload: dict | None = None) -> dict:
    client.put("/api/agent/config", json=config_payload())
    response = client.post("/api/agent/tasks", json=payload or {"prompt": "出一道整数求和题"})
    assert response.status_code == 200, response.text
    task = wait_terminal(client, response.json()["data"]["task_id"])
    assert task["status"] == "success", task
    return task


def test_prompt_only_and_explicit_precedence(agent_client):
    client, _, requests = agent_client
    task = _new_success(client)
    assert task["request"] == {"prompt": "出一道整数求和题"}
    assert task["final_problem"]["problem"]["difficulty"] == "入门"
    assert task["effective_requirements"]["testcase_count"] == 4
    task2 = _new_success(client, {"prompt": "出一道简单题", "difficulty": "困难"})
    assert task2["final_problem"]["problem"]["difficulty"] == "困难"
    prompt = json.loads(json.loads(requests[-1].content)["messages"][1]["content"])
    assert prompt["requirements"] == {"prompt": "出一道简单题", "difficulty": "困难"}
    records = client.get("/api/agent/records", params={"page_size": 1}).json()["data"]
    assert records["total"] == 2 and len(records["items"]) == 1
    assert "reference_solution" not in json.dumps(records)
    assert "testcases" not in json.dumps(records)
    filtered = client.get("/api/agent/records", params={"difficulty": "困难"}).json()["data"]
    assert filtered["total"] == 1


def test_duplicate_create_request_does_not_generate_twice(agent_client):
    client, _, requests = agent_client
    task = _new_success(client, {"prompt": "整数求和", "request_id": "one-submit"})
    before = len(requests)
    response = client.post(
        "/api/agent/tasks", json={"prompt": "整数求和", "request_id": "one-submit"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == task["task_id"]
    assert client.get("/api/agent/records").json()["data"]["total"] == 1
    assert len(requests) == before
    conflict = client.post(
        "/api/agent/tasks", json={"prompt": "另一道题", "request_id": "one-submit"}
    )
    assert conflict.status_code == 409


def test_manual_version_validation_import_and_refine_base(agent_client):
    client, _, requests = agent_client
    original = _new_success(client)
    tid = original["task_id"]
    assert client.post(f"/api/agent/tasks/{tid}/import", json={"confirm": True}).status_code == 200
    edited = deepcopy(original["final_problem"])
    edited["problem"]["title"] = "手动保留的标题"
    edited["problem"]["description"] += " 这是手动添加的说明。"
    result = client.post(f"/api/agent/tasks/{tid}/versions", json={"generated": edited})
    assert result.status_code == 200, result.text
    manual_id = result.json()["data"]["task_id"]
    manual = client.get(f"/api/agent/tasks/{manual_id}").json()["data"]
    assert manual["stage"] == "awaiting_validation" and manual["validation_report"] is None
    assert manual["draft"] == edited
    assert (
        client.post(f"/api/agent/tasks/{manual_id}/import", json={"confirm": True}).status_code
        == 409
    )
    calls_before = len(requests)
    validating = client.post(f"/api/agent/tasks/{manual_id}/validate").json()["data"]["task_id"]
    validated = wait_terminal(client, validating)
    assert validating == manual_id and validated["revision"] == manual["revision"]
    assert validated["status"] == "success"
    assert len(requests) == calls_before  # Validation never calls the model or rewrites content.
    assert validated["final_problem"] == edited
    imported = client.post(
        f"/api/agent/tasks/{validating}/import",
        json={
            "confirm": True,
            "update_existing": True,
            "problem_id": "AI_SUM_1",
        },
    )
    assert imported.status_code == 200, imported.text
    assert client.get("/api/problems/AI_SUM_1").json()["data"]["title"] == "手动保留的标题"
    revised_id = client.post(
        f"/api/agent/tasks/{manual_id}/refine", json={"feedback": "增加一个样例"}
    ).json()["data"]["task_id"]
    revised = wait_terminal(client, revised_id)
    prompt = json.loads(json.loads(requests[-1].content)["messages"][1]["content"])
    assert prompt["previous_draft"] == edited
    assert prompt["revision_feedback"] == "增加一个样例"
    assert revised["base_task_id"] == manual_id
    record = client.get(f"/api/agent/records/{original['record_id']}").json()["data"]
    assert record["version_count"] == 3 and record["imported_problem_id"] == "AI_SUM_1"
    assert len({v["revision"] for v in record["versions"]}) == 3
    assert (
        client.get(f"/api/agent/tasks/{tid}").json()["data"]["final_problem"]
        == original["final_problem"]
    )
    assert (
        client.post(
            f"/api/agent/tasks/{revised_id}/import",
            json={
                "confirm": True,
                "problem_id": "AI_SUM_COPY",
            },
        ).status_code
        == 200
    )


def test_failed_manual_validation_preserves_content_and_last_success(agent_client):
    client, _, requests = agent_client
    original = _new_success(client)
    edited = deepcopy(original["final_problem"])
    edited["problem"]["testcases"][0]["output"] = "999\n"
    before = len(requests)
    response = client.post(
        f"/api/agent/tasks/{original['task_id']}/versions",
        json={"generated": edited, "validate": True},
    )
    task = wait_terminal(client, response.json()["data"]["task_id"])
    assert task["status"] == "error" and task["draft"] == edited
    assert task["final_problem"] is None and len(requests) == before
    records = client.get("/api/agent/records").json()["data"]["items"]
    assert len(records) == 1 and records[0]["status"] == "error"
    assert records[0]["usable_task_id"] == original["task_id"]
    retried = client.post(f"/api/agent/tasks/{task['task_id']}/retry").json()["data"]["task_id"]
    retry = wait_terminal(client, retried)
    assert retried == task["task_id"] and retry["revision"] == task["revision"]
    assert retry["draft"] == edited and retry["status"] == "error"
    assert len(requests) == before


def test_unchanged_saves_and_duplicate_validation_do_not_create_versions(agent_client):
    client, _, requests = agent_client
    original = _new_success(client)
    tid = original["task_id"]
    calls = len(requests)
    for payload in (
        {"generated": original["final_problem"]},
        {"generated": original["final_problem"], "validate": True},
    ):
        response = client.post(f"/api/agent/tasks/{tid}/versions", json=payload)
        assert response.json()["data"] == {"task_id": tid, "status": "success"}
    response = client.post(f"/api/agent/tasks/{tid}/validate")
    assert response.json()["data"] == {"task_id": tid, "status": "success"}
    edited = deepcopy(original["final_problem"])
    edited["problem"]["title"] = "改动后的标题"
    first = client.post(f"/api/agent/tasks/{tid}/versions", json={"generated": edited}).json()[
        "data"
    ]
    duplicate = client.post(f"/api/agent/tasks/{tid}/versions", json={"generated": edited}).json()[
        "data"
    ]
    assert first == duplicate and first["status"] == "draft"
    record = client.get(f"/api/agent/records/{tid}").json()["data"]
    assert record["version_count"] == 2 and len(record["attempts"]) == 2
    assert len(requests) == calls


def test_validation_claim_is_atomic_and_old_version_gets_fresh_execution_budget(
    agent_client, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    client, database, requests = agent_client
    original = _new_success(client)
    edited = deepcopy(original["final_problem"])
    edited["problem"]["title"] = "旧的待验证版本"
    tid = client.post(
        f"/api/agent/tasks/{original['task_id']}/versions", json={"generated": edited}
    ).json()["data"]["task_id"]
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_tasks SET created_at='2020-01-01T00:00:00+00:00' WHERE task_id=?", (tid,)
        )
    tools = client.app.state.agent_task_manager.tools
    original_validate = tools.build_validation_report
    calls = []

    async def delayed_validate(generated):
        calls.append(generated)
        await asyncio.sleep(0.5)
        return await original_validate(generated)

    monkeypatch.setattr(tools, "build_validation_report", delayed_validate)
    before = len(requests)
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda _: client.post(f"/api/agent/tasks/{tid}/validate"), range(2))
        )
    assert all(r.status_code == 200 and r.json()["data"]["task_id"] == tid for r in responses)
    result = wait_terminal(client, tid)
    assert result["status"] == "success" and result["revision"] == 2
    assert result["created_at"].startswith("2020") and not result["execution_queued_at"].startswith(
        "2020"
    )
    assert len(calls) == 1 and len(requests) == before
    record = client.get(f"/api/agent/records/{original['task_id']}").json()["data"]
    assert record["version_count"] == 2


def test_combined_reference_validation_reuses_samples_and_keeps_evidence(agent_client, monkeypatch):
    client, _, _ = agent_client
    tools = client.app.state.agent_task_manager.tools
    original_judge = tools._judge
    calls = []

    async def counted(problem, language, code):
        calls.append((code, len(problem.testcases)))
        return await original_judge(problem, language, code)

    monkeypatch.setattr(tools, "_judge", counted)
    generated = GeneratedProblem.model_validate(generated_problem())
    report = client.portal.call(tools.build_validation_report, generated)
    assert report.reference_all_passed and report.samples_consistent
    assert len(calls) == 2 and all(count == 4 for _, count in calls)
    generated.problem.samples[0].output = "999\n"
    report = client.portal.call(tools.build_validation_report, generated)
    assert report.reference_all_passed and not report.samples_consistent


def test_cancelling_parallel_validation_cleans_up_both_jobs(agent_client, monkeypatch):
    client, _, _ = agent_client
    tools = client.app.state.agent_task_manager.tools
    stopped = []

    async def slow(*args, **kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            stopped.append(True)

    monkeypatch.setattr(tools, "execute_reference_solution", slow)
    monkeypatch.setattr(tools, "evaluate_counterexamples", slow)

    async def run():
        task = asyncio.create_task(
            tools.build_validation_report(GeneratedProblem.model_validate(generated_problem()))
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    client.portal.call(run)
    assert len(stopped) == 2


def test_retry_uses_same_base_and_new_configuration(agent_client):
    client, _, requests = agent_client
    original = _new_success(client)
    transport = client.app.state.agent_model_client.transport
    client.app.state.agent_model_client.transport = httpx.MockTransport(
        lambda request: httpx.Response(503)
    )
    failed_id = client.post(
        f"/api/agent/tasks/{original['task_id']}/refine", json={"feedback": "增加解释"}
    ).json()["data"]["task_id"]
    failed = wait_terminal(client, failed_id)
    assert failed["status"] == "error"
    client.app.state.agent_model_client.transport = transport
    client.put("/api/agent/config", json=config_payload(model_name="replacement-model"))
    retried_id = client.post(f"/api/agent/tasks/{failed_id}/retry").json()["data"]["task_id"]
    retried = wait_terminal(client, retried_id)
    assert retried["status"] == "success" and retried["task_id"] != failed_id
    assert retried["base_task_id"] == original["task_id"]
    assert retried["feedback"] == "增加解释"
    outgoing = json.loads(requests[-1].content)
    assert outgoing["model"] == "replacement-model"
    assert (
        json.loads(outgoing["messages"][1]["content"])["previous_draft"]
        == original["final_problem"]
    )
    assert client.get(f"/api/agent/tasks/{failed_id}").json()["data"]["status"] == "error"


def test_record_serializes_concurrent_requests_and_is_owner_isolated(agent_client):
    from concurrent.futures import ThreadPoolExecutor

    client, _, _ = agent_client
    original = _new_success(client)

    async def delayed(request):
        await asyncio.sleep(0.6)
        return httpx.Response(503)

    client.app.state.agent_model_client.transport = httpx.MockTransport(delayed)
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(
                client.post,
                f"/api/agent/tasks/{original['task_id']}/refine",
                json={"feedback": "增加解释"},
            )
            for _ in range(2)
        ]
        responses = [f.result() for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 409]
    client.post("/api/auth/logout")
    client.post("/api/users/", json={"username": "record-reader", "password": "secret123"})
    client.post("/api/auth/login", json={"username": "record-reader", "password": "secret123"})
    assert client.get("/api/agent/records").json()["data"]["total"] == 0
    assert client.get(f"/api/agent/records/{original['record_id']}").status_code == 404
    for action, body in [
        ("refine", {"feedback": "change"}),
        ("retry", {}),
        ("validate", {}),
        ("versions", {"generated": original["final_problem"]}),
    ]:
        assert (
            client.post(f"/api/agent/tasks/{original['task_id']}/{action}", json=body).status_code
            == 404
        )


def test_legacy_record_backfill_is_idempotent(agent_client):
    client, path, _ = agent_client
    original = _new_success(client)
    edited = deepcopy(original["final_problem"])
    edited["problem"]["title"] = "旧版任务的修改"
    child_id = client.post(
        f"/api/agent/tasks/{original['task_id']}/versions",
        json={"generated": edited},
    ).json()["data"]["task_id"]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE agent_tasks SET record_id=NULL")
    from backend.app.core.database import Database

    asyncio.run(Database(path).initialize())
    asyncio.run(Database(path).initialize())
    record = client.get(f"/api/agent/records/{original['task_id']}").json()["data"]
    assert record["version_count"] == 2
    assert (
        client.get(f"/api/agent/tasks/{child_id}").json()["data"]["record_id"]
        == original["task_id"]
    )


class AgentUIAdapter:
    base_url = "http://agent-test"

    def __init__(self, client):
        self.client = client

    def get(self, path, **kwargs):
        return self._call("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._call("POST", path, **kwargs)

    def _call(self, method, path, **kwargs):
        from frontend.errors import ApiError

        response = self.client.request(method, "/api" + path, **kwargs)
        if response.status_code != 200:
            raise ApiError(response.status_code, response.json()["msg"])
        return response.json()


def test_authoring_drafts_are_cleared_when_changing_account():
    from frontend.session import set_auth_user

    state = {
        "auth_user": {"id": 1},
        "agent_new_draft": {"prompt": "private requirements"},
        "agent_editor_old_title": "private title",
        "agent_create_submission": {"id": "private"},
    }
    set_auth_user({"id": 2}, state)
    assert state == {"auth_user": {"id": 2}}


def test_legacy_requirement_controls_preserve_small_counts_and_deleted_source():
    app = AppTest.from_string("""
from frontend.pages.agent_workspace import requirement_inputs
class Api:
    base_url = "http://legacy-agent-fixture"
    def get(self, path, **kwargs):
        return {"data": []}
requirement_inputs(Api(), "legacy", {
    "prompt": "历史任务", "testcase_count": 1,
    "adapt_existing": True, "existing_problem_id": "deleted-source",
})
""").run()
    assert not app.exception
    assert app.number_input(key="legacy_testcase_count").value == 1
    assert app.selectbox(key="legacy_existing_problem_id").value == "deleted-source"
    assert any("原改编题目已不可用" in warning.value for warning in app.warning)


def _ui(client, task_id=None):
    app = AppTest.from_file(
        Path(__file__).parent / "fixtures" / "agent_pages.py", default_timeout=15
    )
    app.session_state["test_api"] = AgentUIAdapter(client)
    if task_id:
        app.query_params["agent_active_view"] = "任务详情"
        app.query_params["agent_task_id"] = task_id
    return app


def test_ui_prompt_settings_clear_and_history_navigation(agent_client):
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    app = _ui(client).run()
    assert not app.exception
    assert app.number_input(key="agent_new_initial_time_limit").value is None
    assert not any("example_" in (button.key or "") for button in app.button)
    app.text_area(key="agent_new_initial_prompt").set_value("出一道二分查找题").run()
    assert "二分查找" in app.text_area(key="agent_new_initial_prompt").value
    app.selectbox(key="agent_new_initial_difficulty").select("困难").run()
    assert app.session_state["agent_new_draft"]["difficulty"] == "困难"
    app.button(key="agent_new_initial_clear_difficulty").click().run()
    assert "difficulty" not in app.session_state["agent_new_draft"]
    app.button(key="agent_new_initial_submit").click().run()
    assert not app.exception
    tid = app.query_params["agent_task_id"][0]
    task = wait_terminal(client, tid)
    app.run()
    assert not app.exception
    app.query_params["agent_active_view"] = "出题记录"
    app.run()
    assert not app.exception
    assert not any(b.label in ("修改", "重试", "修改要求后重试") for b in app.button)
    app.button(key=f"agent_open_{task['record_id']}").click().run()
    assert not app.exception
    assert app.query_params["agent_task_id"] == [tid]


def test_ui_shared_editor_validate_save_and_explicit_copy(agent_client):
    client, _, _ = agent_client
    task = _new_success(client)
    app = _ui(client, task["task_id"])
    app.query_params["agent_workspace_mode"] = "编辑"
    app.run()
    assert not app.exception
    prefix = f"agent_editor_{task['task_id']}_0"
    app.text_input(key=f"{prefix}_title").set_value("手动标题").run()
    assert any(t.label == "修改意见" for t in app.text_area)
    next(b for b in app.button if b.label == "验证").click().run()
    assert not app.exception
    state = app.session_state[f"agent_working_{task['task_id']}"]
    if state.get("job"):
        wait_terminal(client, state["job"])
    app.run()
    assert not app.exception
    next(b for b in app.button if b.label == "保存").click().run()
    assert not app.exception and app.query_params["agent_task_id"] == [task["task_id"]]
    current = client.get(f"/api/agent/tasks/{task['task_id']}").json()["data"]
    assert current["final_problem"]["problem"]["title"] == "手动标题"
    assert current["revision"] == task["revision"]
    next(b for b in app.button if b.label == "另存为新版本").click().run()
    assert not app.exception
    assert app.query_params["agent_task_id"] != [task["task_id"]]
    assert len(app.selectbox(key="agent_version_selection").options) == 2


def test_record_display_status_filters_latest_version_before_pagination(agent_client):
    client, _, _ = agent_client
    task = _new_success(client)
    tid = task["task_id"]

    def records(state, **extra):
        response = client.get("/api/agent/records", params={"display_status": state, **extra})
        assert response.status_code == 200
        return response.json()["data"]

    assert records("success")["total"] == 1
    assert records("imported")["total"] == 0
    assert client.post(f"/api/agent/tasks/{tid}/import", json={"confirm": True}).status_code == 200
    imported = records("imported")
    assert imported["items"][0]["display_status"] == "imported"
    assert imported["items"][0]["status"] == "success"
    assert records("success")["total"] == 0
    assert (
        client.get("/api/agent/records", params={"status": "success"}).json()["data"]["total"] == 1
    )
    # Historical import must not hide a newer unvalidated or failed version.
    invalid = deepcopy(task["final_problem"])
    invalid["problem"]["testcases"][0]["output"] = "999\n"
    manual = client.post(f"/api/agent/tasks/{tid}/versions", json={"generated": invalid}).json()[
        "data"
    ]
    assert records("draft")["total"] == 1
    assert records("imported")["total"] == 0
    validating = client.post(f"/api/agent/tasks/{manual['task_id']}/validate").json()["data"]
    assert wait_terminal(client, validating["task_id"])["status"] == "error"
    assert records("error")["total"] == 1
    assert records("error")["items"][0]["imported_problem_id"]
    assert records("error", page=2, page_size=1)["total"] == 1
    assert records("error", page=2, page_size=1)["items"] == []
    assert client.get("/api/agent/records", params={"display_status": "invalid"}).status_code == 400


def test_ui_unsaved_navigation_guard_and_import_dialog(agent_client):
    client, _, _ = agent_client
    task = _new_success(client)
    app = _ui(client, task["task_id"]).run()
    assert not app.exception
    # The display page keeps the problem and task information; the dialog appears when editing.
    assert not any(t.label == "修改意见" for t in app.text_area)
    assert not any(b.label in ("AI 修改", "手动编辑") for b in app.button)
    next(b for b in app.button if b.label == "修改").click().run()
    assert any(t.label == "修改意见" for t in app.text_area)
    prefix = f"agent_editor_{task['task_id']}_0"
    app.text_input(key=f"{prefix}_title").set_value("不保存这个标题").run()
    next(b for b in app.button if b.label == "返回出题记录").click().run()
    assert not app.exception
    assert any(b.label == "留在当前页面" for b in app.button)
    next(b for b in app.button if b.label == "留在当前页面").click().run()
    assert app.text_input(key=f"{prefix}_title").value == "不保存这个标题"
    app = _ui(client, task["task_id"]).run()
    next(b for b in app.button if b.label == "导入题目").click().run()
    assert not app.exception
    assert next(b for b in app.button if b.label == "确认导入").disabled
    app.checkbox(key=f"agent_confirm_{task['task_id']}").check().run()
    next(b for b in app.button if b.label == "确认导入").click().run()
    assert not app.exception and app.get("link_button")


def test_ui_failed_task_retries_with_adjusted_requirements_in_workspace(agent_client):
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    transport = client.app.state.agent_model_client.transport
    client.app.state.agent_model_client.transport = httpx.MockTransport(
        lambda request: httpx.Response(503)
    )
    created = client.post("/api/agent/tasks", json={"prompt": "出一道排序题"}).json()["data"]
    assert wait_terminal(client, created["task_id"])["status"] == "error"
    client.app.state.agent_model_client.transport = transport
    app = _ui(client, created["task_id"]).run()
    assert not app.exception
    assert not any(b.label == "按修改后的要求重试" for b in app.button)
    next(b for b in app.button if b.label == "修改要求后重试").click().run()
    prefix = f"agent_requirements_{created['task_id']}"
    app.text_area(key=f"{prefix}_prompt").set_value("出一道二分查找题").run()
    next(b for b in app.button if b.label == "按修改后的要求重试").click().run()
    assert not app.exception
    retry_id = app.query_params["agent_task_id"][0]
    retried = wait_terminal(client, retry_id)
    assert retried["status"] == "success" and retry_id != created["task_id"]
    assert retried["request"]["prompt"] == "出一道二分查找题"


def test_requested_difficulty_and_knowledge_are_kept_as_problem_metadata() -> None:
    request = AuthoringRequest.model_validate(
        {
            "required_knowledge": ["前缀和", "数组"],
            "difficulty": "中等",
            "problem_type": "算法设计",
        }
    )
    result = apply_requested_metadata(GeneratedProblem.model_validate(generated_problem()), request)

    assert result.problem.difficulty == "中等"
    assert result.problem.problem_type == "算法设计"
    assert result.problem.tags[:2] == ["前缀和", "数组"]
    assert "sum" in result.problem.tags


def wait_terminal(client: TestClient, task_id: str) -> dict[str, Any]:
    for _ in range(100):
        task = client.get(f"/api/agent/tasks/{task_id}").json()["data"]
        if task["status"] in {"success", "error", "cancelled"}:
            return task
        time.sleep(0.05)
    raise AssertionError("agent task did not finish")


def test_config_is_encrypted_masked_and_applied(agent_client) -> None:
    client, database, requests = agent_client
    assert client.put("/api/agent/config", json=config_payload()).status_code == 200
    view = client.get("/api/agent/config").json()["data"]
    assert view["has_api_key"] is True and view["masked_api_key"] == "********"
    assert FAKE_KEY not in json.dumps(view)
    assert client.post("/api/agent/config/test").status_code == 200
    assert requests[-1].url == "https://model.example/v1/chat/completions"
    assert requests[-1].headers["authorization"] == f"Bearer {FAKE_KEY}"
    with sqlite3.connect(database) as connection:
        encrypted = connection.execute("SELECT encrypted_api_key FROM agent_config").fetchone()[0]
    assert encrypted != FAKE_KEY and FAKE_KEY not in encrypted


@pytest.mark.parametrize(
    "url",
    ["http://example.com/v1", "https://user:pass@example.com", "https://169.254.169.254"],
)
def test_provider_url_security(url: str) -> None:
    with pytest.raises(ValueError):
        validate_provider_url(url)


def test_missing_encryption_key_does_not_break_oj(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "db",
        problems_path=tmp_path / "problems",
        credential_encryption_key=None,
    )
    with TestClient(create_app(settings)) as client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admintestpassword"})
        response = client.put("/api/agent/config", json=config_payload())
        assert response.status_code == 503
        assert FAKE_KEY not in response.text


def test_agent_end_to_end_events_usage_and_idempotent_import(agent_client) -> None:
    client, _, requests = agent_client
    client.put("/api/agent/config", json=config_payload())
    created = client.post("/api/agent/tasks", json=authoring_payload()).json()["data"]
    assert created["status"] == "pending"
    task = wait_terminal(client, created["task_id"])
    assert task["status"] == "success"
    assert task["input_tokens"] == 100 and task["output_tokens"] == 50
    assert task["total_tokens"] == 150 and task["cost"] == "0.00075"
    assert task["validation_report"]["reference_all_passed"] is True
    assert task["validation_report"]["wrong_solutions_run"] == 1
    events = client.get(f"/api/agent/tasks/{task['task_id']}/events").json()["data"]
    stages = {event["stage"] for event in events}
    assert {"requirement_analysis", "execute_reference", "finalize"} <= stages
    imported = client.post(
        f"/api/agent/tasks/{task['task_id']}/import",
        json={"confirm": True, "update_existing": False},
    )
    assert imported.status_code == 200
    repeated = client.post(
        f"/api/agent/tasks/{task['task_id']}/import",
        json={"confirm": True, "update_existing": False},
    )
    assert repeated.json()["msg"] == "already imported"
    submission_id = client.post(
        "/api/submissions/",
        json={
            "problem_id": "AI_SUM_1",
            "language": "python",
            "code": task["final_problem"]["reference_solution"],
        },
    ).json()["data"]["submission_id"]
    for _ in range(100):
        submission = client.get(f"/api/submissions/{submission_id}").json()["data"]
        if submission["status"] != "pending":
            break
        time.sleep(0.05)
    assert submission["status"] == "success"
    log = client.get(f"/api/submissions/{submission_id}/log").json()["data"]
    assert all(item["result"] == "AC" for item in log["details"])
    assert len(requests) == 1


def test_refine_with_identical_content_keeps_version_but_records_attempt(agent_client) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    parent_id = client.post("/api/agent/tasks", json=authoring_payload()).json()["data"]["task_id"]
    parent = wait_terminal(client, parent_id)
    assert (
        client.post(f"/api/agent/tasks/{parent_id}/import", json={"confirm": True}).status_code
        == 200
    )
    child_id = client.post(
        f"/api/agent/tasks/{parent_id}/refine", json={"feedback": "change background"}
    ).json()["data"]["task_id"]
    child = wait_terminal(client, child_id)
    assert child["parent_task_id"] == parent_id and child["revision"] == parent["revision"]
    assert child["content_version_id"] == parent_id
    record = client.get(f"/api/agent/records/{parent_id}").json()["data"]
    assert record["version_count"] == 1 and len(record["attempts"]) == 2
    assert record["display_status"] == "imported"
    assert child["imported_problem_id"] == "AI_SUM_1"
    assert (
        parent["final_problem"]
        == client.get(f"/api/agent/tasks/{parent_id}").json()["data"]["final_problem"]
    )


def test_pending_task_can_be_cancelled(agent_client) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    task_id = client.post("/api/agent/tasks", json=authoring_payload()).json()["data"]["task_id"]
    assert client.post(f"/api/agent/tasks/{task_id}/cancel").status_code == 200
    assert wait_terminal(client, task_id)["status"] in {"cancelled", "success"}


def test_regular_user_has_isolated_agent_config_and_tasks(agent_client) -> None:
    client, database, _ = agent_client
    assert client.put("/api/agent/config", json=config_payload()).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/users/register", json={"username": "alice", "password": "secret1"})
    client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    empty = client.get("/api/agent/config")
    assert empty.status_code == 200 and empty.json()["data"]["configured"] is False
    assert client.post("/api/agent/tasks", json=authoring_payload()).status_code == 503

    alice_config = config_payload(model_name="alice-model", currency="CNY")
    assert client.put("/api/agent/config", json=alice_config).status_code == 200
    assert client.get("/api/agent/config").json()["data"]["model_name"] == "alice-model"
    alice_task = client.post("/api/agent/tasks", json=authoring_payload()).json()["data"]

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "admin", "password": "admintestpassword"})
    assert client.get("/api/agent/config").json()["data"]["model_name"] == "test-model"
    assert client.get(f"/api/agent/tasks/{alice_task['task_id']}").status_code == 200
    assert all(
        item["task_id"] != alice_task["task_id"]
        for item in client.get("/api/agent/tasks").json()["data"]
    )
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT user_id, model_name FROM agent_config ORDER BY user_id"
        ).fetchall()
    assert rows == [(1, "test-model"), (2, "alice-model")]


def test_legacy_global_agent_config_migrates_to_admin(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO users VALUES (7, 'admin', 'unused', 'admin', '2026-01-01');
            CREATE TABLE agent_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                provider_url TEXT NOT NULL, model_name TEXT NOT NULL,
                encrypted_api_key TEXT NOT NULL, input_price TEXT NOT NULL,
                output_price TEXT NOT NULL, currency TEXT NOT NULL,
                request_timeout REAL NOT NULL, max_iterations INTEGER NOT NULL,
                max_output_tokens INTEGER NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO agent_config VALUES
                (1, 'https://model.example/v1', 'legacy-model', 'ciphertext',
                 '0', '0', 'USD', 60, 3, 4096, '2026-01-01');
            """
        )
    settings = Settings(
        database_path=database,
        problems_path=tmp_path / "problems",
        environment="test",
        credential_encryption_key=Fernet.generate_key().decode(),
    )
    with TestClient(create_app(settings)):
        pass
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_config)").fetchall()
        }
        row = connection.execute("SELECT user_id, model_name FROM agent_config").fetchone()
    assert "user_id" in columns and "id" not in columns
    assert row == (7, "legacy-model")


def test_import_requires_success_and_manual_confirmation(agent_client) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    task_id = client.post("/api/agent/tasks", json=authoring_payload()).json()["data"]["task_id"]
    assert (
        client.post(
            f"/api/agent/tasks/{task_id}/import",
            json={"confirm": False, "update_existing": False},
        ).status_code
        == 400
    )


@pytest.mark.parametrize("status", [401, 429, 500])
def test_model_http_errors_are_structured_and_hide_key(agent_client, status: int) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    client.app.state.agent_model_client.transport = httpx.MockTransport(
        lambda _: httpx.Response(status, text=f"provider error {FAKE_KEY}")
    )
    response = client.post("/api/agent/config/test")
    assert response.status_code == 502
    assert FAKE_KEY not in response.text


def test_invalid_json_is_repaired_and_all_usage_is_retained(agent_client) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "not-json" if calls == 1 else json.dumps(generated_problem())
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    client.app.state.agent_model_client.transport = httpx.MockTransport(handler)
    response = client.post("/api/agent/tasks", json=authoring_payload()).json()
    task = wait_terminal(client, response["data"]["task_id"])
    assert task["status"] == "success" and calls == 2
    assert task["input_tokens"] == 200 and task["output_tokens"] == 100


def test_running_model_request_is_really_cancelled(agent_client) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())

    async def delayed(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json={})

    client.app.state.agent_model_client.transport = httpx.MockTransport(delayed)
    response = client.post("/api/agent/tasks", json=authoring_payload()).json()
    task_id = response["data"]["task_id"]
    for _ in range(100):
        task = client.get(f"/api/agent/tasks/{task_id}").json()["data"]
        if task["status"] == "running":
            break
        time.sleep(0.01)
    assert client.post(f"/api/agent/tasks/{task_id}/cancel").status_code == 200
    assert wait_terminal(client, task_id)["status"] == "cancelled"


@pytest.mark.parametrize("model", ["glm-5.3", "GLM-5.3-FLASH", "test-model"])
def test_model_latency_policy_uses_only_supported_parameters(agent_client, model):
    client, _, requests = agent_client
    client.put("/api/agent/config", json=config_payload(model_name=model, request_timeout=600.0))
    assert client.post("/api/agent/config/test").status_code == 200
    payload = json.loads(requests[-1].content)
    if model.lower().startswith("glm-5.3"):
        assert payload["thinking"] == {"type": "enabled"}
        assert payload["reasoning_effort"] == "low"
    else:
        assert "thinking" not in payload and "reasoning_effort" not in payload
    assert requests[-1].extensions["timeout"]["read"] == 240.0


def test_total_deadline_expires_queued_and_running_tasks_then_worker_recovers(
    agent_client, monkeypatch
):
    from backend.app.modules.agent import task_manager

    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload(request_timeout=600.0))
    original = client.app.state.agent_model_client.transport
    calls, cancelled = [], []

    async def delayed(request):
        calls.append(request)
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
        return httpx.Response(200, json={})

    client.app.state.agent_model_client.transport = httpx.MockTransport(delayed)
    monkeypatch.setattr(task_manager, "TASK_TIME_LIMIT_SECONDS", 1.0)
    first = client.post("/api/agent/tasks", json={"prompt": "first"}).json()["data"]["task_id"]
    monkeypatch.setattr(task_manager, "TASK_TIME_LIMIT_SECONDS", 0.15)
    second = client.post("/api/agent/tasks", json={"prompt": "queued"}).json()["data"]["task_id"]
    queued = wait_terminal(client, second)
    assert queued["error_code"] == "task_timeout" and queued["started_at"] is None
    assert client.get(f"/api/agent/tasks/{first}").json()["data"]["status"] == "running"
    task = wait_terminal(client, first)
    assert task["error_code"] == "task_timeout" and task["status"] == "error"
    assert len(calls) == 1 and cancelled
    assert task["cancellation_requested"] is False
    client.app.state.agent_model_client.transport = original
    monkeypatch.setattr(task_manager, "TASK_TIME_LIMIT_SECONDS", 240.0)
    retried = client.post(f"/api/agent/tasks/{first}/retry").json()["data"]["task_id"]
    assert wait_terminal(client, retried)["status"] == "success"
    assert client.get(f"/api/agent/tasks/{first}").json()["data"]["error_code"] == "task_timeout"


def test_deadline_includes_validation_preserves_draft_and_known_usage(agent_client, monkeypatch):
    from backend.app.modules.agent import task_manager

    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    monkeypatch.setattr(task_manager, "TASK_TIME_LIMIT_SECONDS", 1.0)
    manager = client.app.state.agent_task_manager
    cancelled = []

    async def slow_validation(generated):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(manager.tools, "build_validation_report", slow_validation)
    tid = client.post("/api/agent/tasks", json={"prompt": "test"}).json()["data"]["task_id"]
    task = wait_terminal(client, tid)
    assert task["error_code"] == "task_timeout" and cancelled
    assert task["draft"] and task["final_problem"] is None
    assert task["total_tokens"] == 150 and float(task["cost"]) > 0

    async def late_success():
        from backend.app.modules.agent.models import AgentStatus

        return await manager.repository.update_task(tid, status=AgentStatus.SUCCESS)

    assert client.portal.call(late_success) is False
    assert client.get(f"/api/agent/tasks/{tid}").json()["data"]["status"] == "error"


def test_deadline_does_not_restart_for_json_repair(agent_client, monkeypatch):
    from backend.app.modules.agent import task_manager

    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    monkeypatch.setattr(task_manager, "TASK_TIME_LIMIT_SECONDS", 1.5)
    calls = []

    async def invalid(request):
        calls.append(request)
        await asyncio.sleep(0.1 if len(calls) == 1 else 10)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "invalid json"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    client.app.state.agent_model_client.transport = httpx.MockTransport(invalid)
    tid = client.post("/api/agent/tasks", json={"prompt": "test"}).json()["data"]["task_id"]
    task = wait_terminal(client, tid)
    assert task["error_code"] == "task_timeout" and len(calls) == 2
    assert task["total_tokens"] == 150


def test_recovered_queue_uses_original_creation_time(agent_client):
    client, database, requests = agent_client
    client.put("/api/agent/config", json=config_payload())
    manager = client.app.state.agent_task_manager
    tid = "expired-persisted-task"

    async def persist_only():
        await manager.repository.create_task(tid, 1, AuthoringRequest(prompt="old queued request"))

    client.portal.call(persist_only)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_tasks SET created_at='2020-01-01T00:00:00+00:00' WHERE task_id=?",
            (tid,),
        )
    client.portal.call(manager.enqueue, tid)
    task = wait_terminal(client, tid)
    assert task["error_code"] == "task_timeout" and not requests
    assert task["started_at"] is None


def _editor_check(client, task, content, request_id="editor-check"):
    response = client.post(
        f"/api/agent/tasks/{task['task_id']}/quick-validate",
        json={"generated": content, "request_id": request_id},
    )
    assert response.status_code == 200, response.text
    return wait_terminal(client, response.json()["data"]["task_id"])


def test_editor_check_and_overwrite_preserve_version_and_bind_evidence(agent_client):
    client, _, requests = agent_client
    base = _new_success(client)
    content = deepcopy(base["final_problem"])
    content["problem"]["title"] = "当前未保存草稿"
    content["wrong_solutions"] = ["print(sum(map(int,input().split())))"]
    before = len(requests)
    check = _editor_check(client, base, content)
    assert check["validation_report"]["reference_all_passed"]
    assert check["validation_report"]["wrong_solutions_run"] == 0
    assert check["revision"] == 0 and check["content_version_id"] is None
    unchanged = client.get(f"/api/agent/tasks/{base['task_id']}").json()["data"]
    assert unchanged["final_problem"] == base["final_problem"]
    payload = {
        "generated": content,
        "expected_hash": base["content_hash"],
        "check_id": check["task_id"],
    }
    saved = client.post(f"/api/agent/tasks/{base['task_id']}/save-content", json=payload)
    assert saved.status_code == 200, saved.text
    current = client.get(f"/api/agent/tasks/{base['task_id']}").json()["data"]
    assert current["revision"] == base["revision"] and current["final_problem"] == content
    assert current["stage"] == "finalize" and len(requests) == before
    record = client.get(f"/api/agent/records/{base['task_id']}").json()["data"]
    assert record["version_count"] == 1 and record["latest_task_id"] == base["task_id"]
    stale = deepcopy(content)
    stale["problem"]["description"] += " 再次修改"
    response = client.post(
        f"/api/agent/tasks/{base['task_id']}/save-content",
        json={
            "generated": stale,
            "expected_hash": current["content_hash"],
            "check_id": check["task_id"],
        },
    )
    assert response.status_code == 409
    assert (
        client.post(
            f"/api/agent/tasks/{base['task_id']}/save-content",
            json={"generated": stale, "expected_hash": current["content_hash"]},
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/agent/tasks/{base['task_id']}").json()["data"]["stage"]
        == "awaiting_validation"
    )


def test_editor_save_as_identical_is_explicit_and_idempotent(agent_client):
    client, _, _ = agent_client
    base = _new_success(client)
    payload = {
        "generated": base["final_problem"],
        "expected_hash": base["content_hash"],
        "request_id": "save-copy",
        "force_new": True,
    }
    one = client.post(f"/api/agent/tasks/{base['task_id']}/versions", json=payload)
    assert one.status_code == 200, one.text
    two = client.post(f"/api/agent/tasks/{base['task_id']}/versions", json=payload)
    assert one.json()["data"] == two.json()["data"]
    new_id = one.json()["data"]["task_id"]
    assert new_id != base["task_id"]
    content = deepcopy(base["final_problem"])
    content["problem"]["title"] = "仅覆盖副本"
    current = client.get(f"/api/agent/tasks/{new_id}").json()["data"]
    assert (
        client.post(
            f"/api/agent/tasks/{new_id}/save-content",
            json={"generated": content, "expected_hash": current["content_hash"]},
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/agent/tasks/{base['task_id']}").json()["data"]["final_problem"]
        == base["final_problem"]
    )


def test_editor_detects_stale_windows_and_checks_all_testcases(agent_client):
    client, _, _ = agent_client
    base = _new_success(client)
    bad = deepcopy(base["final_problem"])
    bad["problem"]["testcases"][1]["output"] = "999\n"
    check = _editor_check(client, base, bad)
    report = check["validation_report"]
    assert report["samples_consistent"] and not report["reference_all_passed"]
    assert (
        client.post(
            f"/api/agent/tasks/{base['task_id']}/save-content",
            json={
                "generated": bad,
                "expected_hash": base["content_hash"],
                "check_id": check["task_id"],
            },
        ).status_code
        == 200
    )
    other = deepcopy(base["final_problem"])
    other["problem"]["title"] = "来自旧窗口"
    assert (
        client.post(
            f"/api/agent/tasks/{base['task_id']}/save-content",
            json={"generated": other, "expected_hash": base["content_hash"]},
        ).status_code
        == 409
    )


def test_editor_import_requires_explicit_sync_after_overwrite(agent_client):
    client, _, _ = agent_client
    base = _new_success(client)
    path = f"/api/agent/tasks/{base['task_id']}"
    assert client.post(path + "/import", json={"confirm": True}).status_code == 200
    content = deepcopy(base["final_problem"])
    content["problem"]["title"] = "尚未同步到题库"
    check = _editor_check(client, base, content)
    assert (
        client.post(
            path + "/save-content",
            json={
                "generated": content,
                "expected_hash": base["content_hash"],
                "check_id": check["task_id"],
            },
        ).status_code
        == 200
    )
    current = client.get(path).json()["data"]
    assert not current["import_synced"] and current["imported_problem_id"] == "AI_SUM_1"
    assert (
        client.get("/api/problems/AI_SUM_1").json()["data"]["title"] != content["problem"]["title"]
    )
    assert client.post(path + "/import", json={"confirm": True}).status_code == 409
    assert (
        client.post(
            path + "/import",
            json={"confirm": True, "update_existing": True, "problem_id": "AI_SUM_1"},
        ).status_code
        == 200
    )
    assert client.get(path).json()["data"]["import_synced"]
    assert (
        client.get("/api/problems/AI_SUM_1").json()["data"]["title"] == content["problem"]["title"]
    )


def test_editor_ai_uses_unsaved_draft_without_creating_content_version(agent_client):
    client, _, requests = agent_client
    base = _new_success(client)
    unsaved = deepcopy(base["final_problem"])
    unsaved["problem"]["description"] += " 手工但尚未保存的条件"
    response = client.post(
        f"/api/agent/tasks/{base['task_id']}/refine",
        json={"feedback": "增加解释", "workspace_draft": unsaved, "request_id": "ai-draft"},
    )
    assert response.status_code == 200, response.text
    job = wait_terminal(client, response.json()["data"]["task_id"])
    assert job["status"] == "success" and job["draft"] and job["revision"] == 0
    prompt = json.loads(json.loads(requests[-1].content)["messages"][1]["content"])
    assert prompt["previous_draft"] == unsaved
    current = client.get(f"/api/agent/tasks/{base['task_id']}").json()["data"]
    assert current["final_problem"] == base["final_problem"]
    assert client.get(f"/api/agent/records/{base['task_id']}").json()["data"]["version_count"] == 1


def test_editor_check_busy_deadline_and_cleanup(agent_client, monkeypatch):
    from backend.app.modules.agent import task_manager

    client, _, _ = agent_client
    base = _new_success(client)
    manager = client.app.state.agent_task_manager
    cancelled = []

    async def slow_check(generated, *, reference_only=False):
        assert reference_only
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(task_manager, "TASK_TIME_LIMIT_SECONDS", 0.5)
    monkeypatch.setattr(manager.tools, "build_validation_report", slow_check)
    path = f"/api/agent/tasks/{base['task_id']}"
    payload = {"generated": base["final_problem"], "request_id": "slow-check"}
    response = client.post(path + "/quick-validate", json=payload)
    assert response.status_code == 200
    repeated = client.post(path + "/quick-validate", json=payload)
    assert repeated.json()["data"]["task_id"] == response.json()["data"]["task_id"]
    assert (
        client.post(
            path + "/save-content",
            json={"generated": base["final_problem"], "expected_hash": base["content_hash"]},
        ).status_code
        == 409
    )
    job = wait_terminal(client, response.json()["data"]["task_id"])
    assert job["error_code"] == "task_timeout" and cancelled
    assert client.get(path).json()["data"]["final_problem"] == base["final_problem"]


def test_editor_routes_are_owner_isolated(agent_client):
    client, _, _ = agent_client
    base = _new_success(client)
    path = f"/api/agent/tasks/{base['task_id']}"
    client.post("/api/auth/logout")
    client.post("/api/users/register", json={"username": "editor-other", "password": "secret123"})
    client.post("/api/auth/login", json={"username": "editor-other", "password": "secret123"})
    assert (
        client.post(
            path + "/quick-validate",
            json={"generated": base["final_problem"], "request_id": "foreign-check"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            path + "/save-content",
            json={"generated": base["final_problem"], "expected_hash": base["content_hash"]},
        ).status_code
        == 404
    )
