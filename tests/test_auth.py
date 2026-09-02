"""Authentication, authorization, and persistence tests."""

import inspect
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import bcrypt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.users.dependencies import require_admin
from backend.app.modules.users.models import User
from backend.app.modules.users.router import router as users_router


@pytest.fixture
def auth_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    database_path = tmp_path / "oj.sqlite3"
    settings = Settings(database_path=database_path, environment="test")
    application = create_app(settings)

    @application.get("/test/admin")
    async def admin_only(_: Annotated[User, Depends(require_admin)]) -> dict[str, bool]:
        return {"ok": True}

    with TestClient(application) as client:
        yield client, database_path


def _register(client: TestClient, username: str = "alice", password: str = "secret1"):
    return client.post(
        "/api/users/register",
        json={"username": username, "password": password},
    )


def _login(client: TestClient, username: str = "alice", password: str = "secret1"):
    return client.post(
        "/api/users/login",
        json={"username": username, "password": password},
    )


def test_first_start_creates_bcrypt_admin(auth_client: tuple[TestClient, Path]) -> None:
    client, database_path = auth_client

    response = _login(client, "admin", "admintestpassword")

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"
    with sqlite3.connect(database_path) as connection:
        password_hash, role = connection.execute(
            "SELECT password_hash, role FROM users WHERE username = 'admin'"
        ).fetchone()
    assert role == "admin"
    assert password_hash != "admintestpassword"
    assert bcrypt.checkpw(b"admintestpassword", password_hash.encode("ascii"))


def test_register_returns_only_public_user(auth_client: tuple[TestClient, Path]) -> None:
    client, _ = auth_client

    response = _register(client)

    assert response.status_code == 200
    assert response.json()["data"]["username"] == "alice"
    assert response.json()["data"]["role"] == "user"
    assert "password" not in response.text.lower()
    assert "session" not in response.text.lower()


def test_duplicate_username_returns_400(auth_client: tuple[TestClient, Path]) -> None:
    client, _ = auth_client
    assert _register(client).status_code == 200

    response = _register(client)

    assert response.status_code == 400
    assert response.json() == {
        "code": 400,
        "msg": "Username already exists",
        "data": None,
    }


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("ab", "secret1"),
        ("a" * 41, "secret1"),
        ("alice", "s3cr!"),
    ],
)
def test_invalid_credentials_return_safe_400(
    auth_client: tuple[TestClient, Path],
    username: str,
    password: str,
) -> None:
    client, _ = auth_client

    response = _register(client, username, password)

    assert response.status_code == 400
    assert response.json()["code"] == 400
    assert password not in response.text


def test_login_accepts_correct_and_rejects_wrong_password(
    auth_client: tuple[TestClient, Path],
) -> None:
    client, _ = auth_client
    _register(client)

    wrong = _login(client, password="not-the-password")
    correct = _login(client)

    assert wrong.status_code == 401
    assert wrong.json()["msg"] == "Invalid username or password"
    assert correct.status_code == 200


def test_httponly_cookie_maintains_login_and_logout_invalidates_session(
    auth_client: tuple[TestClient, Path],
) -> None:
    client, _ = auth_client
    _register(client)

    login = _login(client)
    session_id = client.cookies.get("session_id")
    me = client.get("/api/users/me")
    logout = client.post("/api/users/logout")
    after_logout = client.get("/api/users/me")

    assert login.status_code == 200
    assert session_id
    assert "httponly" in login.headers["set-cookie"].lower()
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "alice"
    assert logout.status_code == 200
    assert after_logout.status_code == 401


def test_regular_user_cannot_use_admin_dependency(
    auth_client: tuple[TestClient, Path],
) -> None:
    client, _ = auth_client
    _register(client)
    _login(client)

    response = client.get("/test/admin")

    assert response.status_code == 403
    assert response.json() == {"code": 403, "msg": "Permission denied", "data": None}


def test_banned_user_cannot_login(auth_client: tuple[TestClient, Path]) -> None:
    client, database_path = auth_client
    _register(client)
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE users SET role = 'banned' WHERE username = 'alice'")
        connection.commit()

    response = _login(client)

    assert response.status_code == 403
    assert response.json()["msg"] == "User is banned"
    assert client.cookies.get("session_id") is None


def test_responses_logs_and_database_do_not_expose_secrets(
    auth_client: tuple[TestClient, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, database_path = auth_client
    password = "highly-secret-password"
    _register(client, password=password)
    caplog.set_level(logging.DEBUG)

    response = _login(client, password=password)
    session_id = client.cookies.get("session_id")

    with sqlite3.connect(database_path) as connection:
        password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()[0]
        stored_session = connection.execute("SELECT id_hash FROM sessions").fetchone()[0]

    assert response.status_code == 200
    assert session_id
    assert password not in response.text
    assert password_hash not in response.text
    assert session_id not in response.text
    assert password not in caplog.text
    assert password_hash not in caplog.text
    assert session_id not in caplog.text
    assert stored_session != session_id


def test_users_survive_application_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "persistent.sqlite3"
    settings = Settings(database_path=database_path, environment="test")

    with TestClient(create_app(settings)) as first_client:
        assert _register(first_client).status_code == 200

    with TestClient(create_app(settings)) as restarted_client:
        response = _login(restarted_client)

    assert response.status_code == 200
    assert response.json()["data"]["username"] == "alice"


def test_authentication_route_handlers_are_async(tmp_path: Path) -> None:
    application = create_app(Settings(database_path=tmp_path / "async.sqlite3"))
    auth_paths = {
        "/api/users/register",
        "/api/users/login",
        "/api/users/logout",
        "/api/users/me",
    }

    del application
    endpoints = {
        f"/api/users{route.path}": route.endpoint
        for route in users_router.routes
        if hasattr(route, "endpoint")
    }

    assert set(endpoints) == auth_paths
    assert all(inspect.iscoroutinefunction(endpoint) for endpoint in endpoints.values())
