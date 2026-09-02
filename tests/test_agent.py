"""Advance AI authoring security, lifecycle, usage, cancellation, and import tests."""

import asyncio
import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.agent.models import validate_provider_url

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
    settings = Settings(database_path=tmp_path / "db", problems_path=tmp_path / "problems")
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


def test_regular_user_cannot_access_agent(agent_client) -> None:
    client, _, _ = agent_client
    client.post("/api/auth/logout")
    client.post("/api/users/register", json={"username": "alice", "password": "secret1"})
    client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert client.get("/api/agent/config").status_code == 403
    assert client.post("/api/agent/tasks", json=authoring_payload()).status_code == 403


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
