"""Language registry API, validation, and persistence tests."""

import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.judge.router import router as language_router


@pytest.fixture
def language_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_path=tmp_path / "oj.sqlite3",
        problems_path=tmp_path / "problems",
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        yield client


def login(client: TestClient) -> None:
    assert client.post(
        "/api/users/register", json={"username": "alice", "password": "secret1"}
    ).status_code == 200
    assert client.post(
        "/api/users/login", json={"username": "alice", "password": "secret1"}
    ).status_code == 200


def test_default_languages_are_listed(language_client: TestClient) -> None:
    response = language_client.get("/api/languages/")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "msg": "success",
        "data": {"name": ["python", "cpp"]},
    }


def test_logged_in_user_can_register_language(language_client: TestClient) -> None:
    login(language_client)

    response = language_client.post(
        "/api/languages/",
        json={
            "name": "ruby",
            "file_ext": ".rb",
            "run_cmd": "ruby {src}",
            "time_limit": 2.0,
            "memory_limit": 256,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "msg": "language registered",
        "data": {"name": "ruby"},
    }
    assert language_client.get("/api/languages/").json()["data"]["name"] == [
        "python",
        "cpp",
        "ruby",
    ]


def test_duplicate_language_name_returns_400(language_client: TestClient) -> None:
    login(language_client)

    response = language_client.post(
        "/api/languages/",
        json={"name": "python", "file_ext": ".py", "run_cmd": "python {src}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "bad name", "file_ext": ".x", "run_cmd": "tool {src}"},
        {"name": "badext", "file_ext": "../x", "run_cmd": "tool {src}"},
        {"name": "shell", "file_ext": ".x", "run_cmd": "tool {src}; whoami"},
        {"name": "pipe", "file_ext": ".x", "run_cmd": "tool {src} | other"},
        {"name": "unknown", "file_ext": ".x", "run_cmd": "tool {code}"},
        {"name": "missing", "file_ext": ".x", "run_cmd": "tool"},
        {
            "name": "compiled",
            "file_ext": ".x",
            "compile_cmd": "compiler {src}",
            "run_cmd": "{exe}",
        },
    ],
)
def test_invalid_language_configuration_returns_400(
    language_client: TestClient, payload: dict[str, object]
) -> None:
    login(language_client)

    response = language_client.post("/api/languages/", json=payload)

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_register_language_requires_login(language_client: TestClient) -> None:
    response = language_client.post(
        "/api/languages/",
        json={"name": "ruby", "file_ext": ".rb", "run_cmd": "ruby {src}"},
    )

    assert response.status_code == 401


def test_language_survives_restart(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "persistent.sqlite3",
        problems_path=tmp_path / "problems",
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        login(client)
        assert client.post(
            "/api/languages/",
            json={"name": "ruby", "file_ext": ".rb", "run_cmd": "ruby {src}"},
        ).status_code == 200

    with TestClient(create_app(settings)) as restarted:
        names = restarted.get("/api/languages/").json()["data"]["name"]

    assert "ruby" in names


def test_language_route_handlers_are_async() -> None:
    endpoints = [route.endpoint for route in language_router.routes if hasattr(route, "endpoint")]

    assert len(endpoints) == 2
    assert all(inspect.iscoroutinefunction(endpoint) for endpoint in endpoints)
