"""Collection API ownership, transaction and persistence regressions."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app

ROOT = "/api/problem-banks/"
PROBLEM = {
    "id": "P1",
    "title": "Sum",
    "description": "Add",
    "input_description": "Two numbers",
    "output_description": "Sum",
    "constraints": "Small numbers",
    "samples": [{"input": "1 2", "output": "3"}],
    "testcases": [{"input": "1 2", "output": "3"}],
}


def login(client, username="alice"):
    password = "admintestpassword" if username == "admin" else "secret1"
    if username != "admin":
        client.post("/api/users/", json={"username": username, "password": password})
    assert (
        client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": password,
            },
        ).status_code
        == 200
    )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_path=tmp_path / "oj.db", problems_path=tmp_path / "problems", environment="test"
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        login(client)
        for pid in ("P1", "P2"):
            assert client.post("/api/problems/", json={**PROBLEM, "id": pid}).status_code == 200
        yield client


def create(client, name="练习"):
    response = client.post(ROOT, json={"name": name, "description": "描述"})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def ids(client, bank):
    response = client.get(f"{ROOT}{bank}")
    assert response.status_code == 200, response.text
    return [p["id"] for p in response.json()["data"]["problems"]]


def add(client, bank, *pids):
    return client.post(f"{ROOT}{bank}/problems", json={"problem_ids": list(pids)})


def test_crud_names_and_cascade(client, settings):
    first = create(client, "  动态规划  ")
    second = create(client, "图论")
    assert client.post(ROOT, json={"name": "动态规划"}).status_code == 409
    assert client.put(f"{ROOT}{second}", json={"name": "动态规划"}).status_code == 409
    for payload in ({"name": " "}, {"name": "a" * 41}, {"name": "ok", "description": "x" * 201}):
        assert client.post(ROOT, json=payload).status_code == 400
    assert (
        client.put(f"{ROOT}{first}", json={"name": "复习", "description": "新描述"}).status_code
        == 200
    )
    assert add(client, first, "P1", "P1").status_code == 200
    assert add(client, first, "P1").status_code == 200
    banks = client.get(ROOT).json()["data"]
    assert [b["id"] for b in banks] == [second, first]
    assert banks[1]["problem_count"] == 1
    assert banks[1]["description"] == "新描述"
    assert client.delete(f"{ROOT}{first}").status_code == 200
    assert client.get(f"{ROOT}{first}").status_code == 404
    assert client.get("/api/problems/P1").status_code == 200
    with sqlite3.connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM problem_bank_items").fetchone()[0] == 0


def test_batch_atomicity_and_move(client):
    source, target = create(client, "source"), create(client, "target")
    assert add(client, source, "P1", "missing").status_code == 404
    assert ids(client, source) == []
    assert add(client, source, "P2", "P1").status_code == 200
    assert add(client, target, "P1").status_code == 200
    move = f"{ROOT}{source}/problems/move"
    assert (
        client.post(move, json={"problem_ids": ["P1"], "target_bank_id": source}).status_code == 400
    )
    assert (
        client.post(
            move,
            json={
                "problem_ids": ["P1", "missing"],
                "target_bank_id": target,
            },
        ).status_code
        == 400
    )
    assert ids(client, source) == ["P1", "P2"]
    assert ids(client, target) == ["P1"]
    assert (
        client.post(
            move,
            json={
                "problem_ids": ["P1", "P2", "P2"],
                "target_bank_id": target,
            },
        ).status_code
        == 200
    )
    assert ids(client, source) == []
    assert ids(client, target) == ["P1", "P2"]
    for _ in range(2):
        assert (
            client.post(
                f"{ROOT}{target}/problems/remove",
                json={
                    "problem_ids": ["P1", "missing"],
                },
            ).status_code
            == 200
        )
    assert ids(client, target) == ["P2"]
    for invalid in ([], ["../bad"]):
        assert (
            client.post(f"{ROOT}{target}/problems", json={"problem_ids": invalid}).status_code
            == 400
        )


def test_owner_isolation_including_admin(client):
    private = create(client)
    assert add(client, private, "P1").status_code == 200
    for username in ("bob", "admin"):
        login(client, username)
        assert client.get(ROOT).json()["data"] == []
        own = create(client)
        assert add(client, own, "P1").status_code == 200
        for method, suffix, payload in (
            ("GET", "", None),
            ("PUT", "", {"name": "stolen"}),
            ("DELETE", "", None),
            ("POST", "/problems", {"problem_ids": ["P1"]}),
            ("POST", "/problems/remove", {"problem_ids": ["P1"]}),
            ("POST", "/problems/move", {"problem_ids": ["P1"], "target_bank_id": own}),
        ):
            assert (
                client.request(method, f"{ROOT}{private}{suffix}", json=payload).status_code == 404
            )
        assert (
            client.post(
                f"{ROOT}{own}/problems/move",
                json={
                    "problem_ids": ["P1"],
                    "target_bank_id": private,
                },
            ).status_code
            == 404
        )
        assert ids(client, own) == ["P1"]
    client.post("/api/auth/logout")
    for method, suffix, payload in (
        ("GET", "", None),
        ("POST", "", {"name": "new"}),
        ("GET", str(private), None),
        ("PUT", str(private), {"name": "new"}),
        ("DELETE", str(private), None),
        ("POST", f"{private}/problems", {"problem_ids": ["P1"]}),
        ("POST", f"{private}/problems/remove", {"problem_ids": ["P1"]}),
        ("POST", f"{private}/problems/move", {"problem_ids": ["P1"], "target_bank_id": own}),
    ):
        assert client.request(method, ROOT + suffix, json=payload).status_code == 401


def test_live_metadata_deleted_problem_and_restart(settings):
    with TestClient(create_app(settings)) as client:
        login(client)
        client.post("/api/problems/", json=PROBLEM)
        bank, target = create(client), create(client, "target")
        add(client, bank, "P1")
        client.put("/api/problems/P1", json={**PROBLEM, "title": "Changed"})
        assert client.get(f"{ROOT}{bank}").json()["data"]["problems"][0]["title"] == "Changed"
    with TestClient(create_app(settings)) as client:
        login(client)
        assert ids(client, bank) == ["P1"]
        login(client, "admin")
        assert client.delete("/api/problems/P1").status_code == 200
        login(client)
        data = client.get(f"{ROOT}{bank}").json()["data"]
        assert data["problem_count"] == 1
        assert data["problems"] == [{"id": "P1", "title": "题目已删除", "available": False}]
        assert (
            client.post(
                f"{ROOT}{bank}/problems/move",
                json={
                    "problem_ids": ["P1"],
                    "target_bank_id": target,
                },
            ).status_code
            == 404
        )
        assert ids(client, bank) == ["P1"]
        assert ids(client, target) == []
        assert (
            client.post(f"{ROOT}{bank}/problems/remove", json={"problem_ids": ["P1"]}).status_code
            == 200
        )
        assert ids(client, bank) == []


def test_creation_with_selected_problems_is_atomic(client):
    response = client.post(ROOT, json={"name": "草稿", "problem_ids": ["P1", "missing"]})
    assert response.status_code == 404
    assert client.get(ROOT).json()["data"] == []
    response = client.post(ROOT, json={"name": "草稿", "problem_ids": ["P1", "P2", "P1"]})
    assert response.status_code == 200
    bank_id = response.json()["data"]["id"]
    assert ids(client, bank_id) == ["P1", "P2"]
    assert client.post(ROOT, json={"name": "草稿", "problem_ids": ["P1"]}).status_code == 409
    assert ids(client, bank_id) == ["P1", "P2"]
