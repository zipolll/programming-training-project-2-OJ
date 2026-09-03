"""Step 4/5 user administration, evaluation-log, audit, and migration tests."""

import asyncio
import inspect
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.main import create_app
from backend.app.modules.logs.router import problem_log_router, router, submission_log_router
from backend.app.modules.users.auth_router import router as auth_router
from backend.app.modules.users.management_router import router as management_router


def _problem(problem_id: str = "P1") -> dict[str, object]:
    return {
        "id": problem_id,
        "title": "A+B",
        "description": "Add.",
        "input_description": "Two ints.",
        "output_description": "One int.",
        "samples": [{"input": "1 2", "output": "3"}],
        "constraints": "integers",
        "testcases": [{"input": "1 2", "output": "3"}],
    }


@pytest.fixture
def context(tmp_path: Path) -> Iterator[tuple[TestClient, FastAPI, Path]]:
    database_path = tmp_path / "oj.sqlite3"
    app = create_app(
        Settings(
            database_path=database_path,
            problems_path=tmp_path / "problems",
            environment="test",
            submission_rate_limit_per_minute=100,
        )
    )
    with TestClient(app) as client:
        yield client, app, database_path


def _register(client: TestClient, username: str) -> int:
    response = client.post(
        "/api/users/", json={"username": username, "password": "secret1"}
    )
    assert response.status_code == 200
    return int(response.json()["data"]["user_id"])


def _login(client: TestClient, username: str, password: str = "secret1") -> None:
    assert client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).status_code == 200


def _admin(client: TestClient) -> None:
    _login(client, "admin", "admintestpassword")


def _insert_submission(
    database_path: Path,
    *,
    user_id: int,
    problem_id: str = "P1",
    result: str = "AC",
    version: int = 1,
) -> int:
    now = "2026-09-02T01:02:03+00:00"
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO submissions
                (user_id, problem_id, language, code, status, result, score, counts,
                 created_at, updated_at, finished_at, evaluation_version)
            VALUES (?, ?, 'python', 'print(3)', 'success', ?, ?, 10, ?, ?, ?, ?)
            """,
            (user_id, problem_id, result, 10 if result == "AC" else 0, now, now, now, version),
        )
        submission_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO submission_testcases
                (submission_id, evaluation_version, testcase_id, result,
                 time, memory, error_summary)
            VALUES (?, ?, 1, ?, 0.01, 2.0, ?)
            """,
            (submission_id, version, result, "runtime summary" if result == "RE" else ""),
        )
        connection.commit()
    return submission_id


def test_user_info_permissions_pagination_and_statistics(
    context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, _, database_path = context
    alice_id = _register(client, "alice")
    bob_id = _register(client, "bobby")
    _insert_submission(database_path, user_id=alice_id, problem_id="P1", result="AC")
    _insert_submission(database_path, user_id=alice_id, problem_id="P1", result="AC")
    _insert_submission(database_path, user_id=alice_id, problem_id="P2", result="WA")
    with sqlite3.connect(database_path) as connection:
        now = "2026-09-02T01:02:03+00:00"
        connection.execute(
            """
            INSERT INTO submissions
                (user_id, problem_id, language, code, status, counts,
                 created_at, updated_at, evaluation_version)
            VALUES (?, 'P3', 'python', 'x', 'pending', 10, ?, ?, 1)
            """,
            (alice_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO submissions
                (user_id, problem_id, language, code, status, counts,
                 created_at, updated_at, finished_at, evaluation_version)
            VALUES (?, 'P4', 'python', 'x', 'error', 10, ?, ?, ?, 1)
            """,
            (alice_id, now, now, now),
        )
        connection.commit()

    _login(client, "alice")
    own = client.get(f"/api/users/{alice_id}")
    assert own.status_code == 200
    assert own.json()["data"]["submit_count"] == 5
    assert own.json()["data"]["resolve_count"] == 1
    assert not {"password", "password_hash", "session_id"} & set(own.json()["data"])
    assert client.get(f"/api/users/{bob_id}").status_code == 403
    assert client.get("/api/users/999999").status_code == 403

    _admin(client)
    page = client.get("/api/users/?page=2&page_size=1")
    assert page.status_code == 200
    assert page.json()["data"]["total"] == 3
    assert len(page.json()["data"]["users"]) == 1
    assert client.get("/api/users/?page=1").status_code == 400
    assert client.get("/api/users/999999").status_code == 404


def test_role_changes_ban_sessions_and_preserve_last_admin(
    context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, _, database_path = context
    alice_id = _register(client, "alice")
    _login(client, "alice")
    alice_session = client.cookies.get("session_id")
    assert alice_session
    assert client.put(f"/api/users/{alice_id}/role", json={"role": "admin"}).status_code == 403

    _admin(client)
    assert client.put(f"/api/users/{alice_id}/role", json={"role": "invalid"}).status_code == 400
    assert client.put("/api/users/999999/role", json={"role": "user"}).status_code == 404
    assert client.put("/api/users/1/role", json={"role": "user"}).status_code == 409
    changed = client.put(f"/api/users/{alice_id}/role", json={"role": "banned"})
    assert changed.status_code == 200

    client.cookies.clear()
    client.cookies.set("session_id", alice_session)
    assert client.get("/api/problems/").status_code == 401
    assert client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    ).status_code == 403
    with sqlite3.connect(database_path) as connection:
        sessions = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (alice_id,)
        ).fetchone()[0]
        changes = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT changes FROM audit_logs WHERE action = 'update_user_role'"
            )
        ]
    assert sessions == 0
    assert {"before": "user", "after": "banned"} in changes
    client.cookies.clear()
    _admin(client)
    assert client.put(f"/api/users/{alice_id}/role", json={"role": "user"}).status_code == 200
    _login(client, "alice")
    with sqlite3.connect(database_path) as connection:
        changes = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT changes FROM audit_logs WHERE action = 'update_user_role'"
            )
        ]
    assert {"before": "banned", "after": "user"} in changes


def test_log_visibility_access_clipping_and_access_audit(
    context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, _, database_path = context
    alice_id = _register(client, "alice")
    _login(client, "alice")
    assert client.post("/api/problems/", json=_problem()).status_code == 200
    submission_id = _insert_submission(
        database_path, user_id=alice_id, result="RE", version=2
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO submission_testcases
                (submission_id, evaluation_version, testcase_id, result,
                 time, memory, error_summary)
            VALUES (?, 1, 1, 'WA', 9.0, 9.0, 'stale result')
            """,
            (submission_id,),
        )
        connection.commit()

    owner = client.get(f"/api/submissions/{submission_id}/log")
    assert owner.status_code == 200
    assert owner.json()["data"] == {
        "details": [
            {
                "id": 1,
                "result": "RE",
                "time": 0.01,
                "memory": 2.0,
                "error_summary": "runtime summary",
            }
        ],
        "score": 0,
        "counts": 10,
    }

    _register(client, "bobby")
    _login(client, "bobby")
    denied = client.get(f"/api/submissions/{submission_id}/log")
    assert denied.status_code == 403
    assert denied.json()["data"] is None
    assert "details" not in denied.text

    _admin(client)
    assert client.get(f"/api/submissions/{submission_id}/log").status_code == 200
    visible = client.put("/api/problems/P1/log_visibility", json={"public_cases": True})
    assert visible.status_code == 200
    _login(client, "bobby")
    assert client.get(f"/api/submissions/{submission_id}/log").status_code == 200
    assert client.get(f"/api/submissions/{submission_id}").status_code == 403
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get(f"/api/submissions/{submission_id}/log").status_code == 401

    _admin(client)
    access = client.get("/api/logs/access/?problem_id=P1")
    assert access.status_code == 200
    assert {item["status"] for item in access.json()["data"]} >= {"200", "403"}
    private = client.put("/api/problems/P1/log_visibility", json={"public_cases": False})
    assert private.status_code == 200
    _login(client, "bobby")
    assert client.get(f"/api/submissions/{submission_id}/log").status_code == 403


def test_privileged_actions_are_structurally_audited(
    context: tuple[TestClient, FastAPI, Path],
) -> None:
    client, _, database_path = context
    alice_id = _register(client, "alice")
    _login(client, "alice")
    assert client.post("/api/problems/", json=_problem()).status_code == 200
    submission_id = _insert_submission(database_path, user_id=alice_id)
    _admin(client)
    assert client.put(
        "/api/problems/P1/log_visibility", json={"public_cases": True}
    ).status_code == 200
    assert client.put(f"/api/submissions/{submission_id}/rejudge").status_code == 200
    assert client.delete("/api/problems/P1").status_code == 200
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT action, changes FROM audit_logs ORDER BY id"
        ).fetchall()
    actions = {row[0] for row in rows}
    assert {"update_log_visibility", "rejudge_submission", "delete_problem"} <= actions
    serialized = " ".join(row[1] for row in rows).lower()
    assert all(secret not in serialized for secret in ("password", "session", "cookie", "print(3)"))


def test_schema_upgrade_is_idempotent_and_preserves_users(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO users VALUES (1, 'kept', 'hash', 'user', '2026-01-01T00:00:00+00:00')"
        )
        connection.commit()

    database = Database(path)
    asyncio.run(database.initialize())
    asyncio.run(database.initialize())
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT username FROM users").fetchall() == [("kept",)]
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"problem_log_visibility", "audit_logs", "submission_testcases"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM problem_log_visibility").fetchone()[0] == 0


def test_new_route_handlers_are_async() -> None:
    routes = [
        *auth_router.routes,
        *management_router.routes,
        *router.routes,
        *submission_log_router.routes,
        *problem_log_router.routes,
    ]
    assert routes
    assert all(inspect.iscoroutinefunction(route.endpoint) for route in routes)
