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
    assert config.request_timeout == 360.0
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
    assert record["version_count"] == 4 and record["imported_problem_id"] == "AI_SUM_1"
    assert len({v["revision"] for v in record["versions"]}) == 4
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
    assert retry["draft"] == edited and retry["status"] == "error"
    assert len(requests) == before


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
    child_id = client.post(
        f"/api/agent/tasks/{original['task_id']}/versions",
        json={"generated": original["final_problem"]},
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
        'auth_user': {'id': 1}, 'agent_new_draft': {'prompt': 'private requirements'},
        'agent_editor_old_title': 'private title', 'agent_create_submission': {'id': 'private'},
    }
    set_auth_user({'id': 2}, state)
    assert state == {'auth_user': {'id': 2}}


def test_legacy_requirement_controls_preserve_small_counts_and_deleted_source():
    app = AppTest.from_string('''
from frontend.pages.agent_workspace import requirement_inputs
class Api:
    base_url = "http://legacy-agent-fixture"
    def get(self, path, **kwargs):
        return {"data": []}
requirement_inputs(Api(), "legacy", {
    "prompt": "历史任务", "testcase_count": 1,
    "adapt_existing": True, "existing_problem_id": "deleted-source",
})
''').run()
    assert not app.exception
    assert app.number_input(key='legacy_testcase_count').value == 1
    assert app.selectbox(key='legacy_existing_problem_id').value == 'deleted-source'
    assert any('原改编题目已不可用' in warning.value for warning in app.warning)


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
    app.button(key="agent_new_initial_example_算法入门").click().run()
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
    app.button(key=f"agent_open_{task['record_id']}").click().run()
    assert not app.exception
    assert app.query_params["agent_task_id"] == [tid]


def test_ui_manual_edit_save_switch_versions_and_narrow_panes(agent_client, monkeypatch):
    from types import SimpleNamespace

    from frontend.pages import agent_workspace

    client, _, _ = agent_client
    task = _new_success(client)
    app = _ui(client, task["task_id"])
    app.query_params["agent_workspace_mode"] = "编辑"
    app.run()
    assert not app.exception
    prefix = f"agent_editor_{task['task_id']}"
    app.text_input(key=f"{prefix}_title").set_value("手动标题")
    next(b for b in app.button if b.label == "保存新版本").click().run()
    assert not app.exception
    manual_id = app.query_params["agent_task_id"][0]
    manual = client.get(f"/api/agent/tasks/{manual_id}").json()["data"]
    assert manual["draft"]["problem"]["title"] == "手动标题"
    app.selectbox(key="agent_version_selection").select(task["task_id"]).run()
    assert app.query_params["agent_task_id"] == [task["task_id"]]
    app.selectbox(key="agent_version_selection").select(manual_id).run()
    assert app.query_params["agent_task_id"] == [manual_id]
    monkeypatch.setattr(
        agent_workspace, "_viewport", lambda **kwargs: SimpleNamespace(compact=True)
    )
    app.run()
    assert not app.exception
    assert any(t.label == "继续修改" for t in app.text_area)
    app.session_state["agent_compact_pane"] = "题目"
    app.run()
    assert not app.exception
    assert not any(t.label == "继续修改" for t in app.text_area)


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


def test_refine_creates_child_revision(agent_client) -> None:
    client, _, _ = agent_client
    client.put("/api/agent/config", json=config_payload())
    parent_id = client.post("/api/agent/tasks", json=authoring_payload()).json()["data"]["task_id"]
    parent = wait_terminal(client, parent_id)
    child_id = client.post(
        f"/api/agent/tasks/{parent_id}/refine", json={"feedback": "change background"}
    ).json()["data"]["task_id"]
    child = wait_terminal(client, child_id)
    assert child["parent_task_id"] == parent_id and child["revision"] == 2
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
