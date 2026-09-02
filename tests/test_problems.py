"""Problem schema, persistence, API, and permission tests."""

import inspect
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.problems.repository import validate_problem_id
from backend.app.modules.problems.router import router as problems_router


@pytest.fixture
def problem_data() -> dict[str, object]:
    return {
        "id": "P1001",
        "title": "A+B Problem",
        "description": "Add two integers.",
        "input_description": "Two integers.",
        "output_description": "Their sum.",
        "samples": [{"input": "1 2", "output": "3"}],
        "constraints": "|a|, |b| <= 10^9",
        "testcases": [{"input": "-1 2", "output": "1"}],
        "hint": "Negative numbers are possible.",
        "source": "course",
        "tags": ["math"],
        "time_limit": 1.0,
        "memory_limit": 128,
        "author": "teacher",
        "difficulty": "beginner",
    }


@pytest.fixture
def problem_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    problems_path = tmp_path / "problems"
    settings = Settings(
        database_path=tmp_path / "oj.sqlite3",
        problems_path=problems_path,
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        yield client, problems_path


def _register_and_login(client: TestClient) -> None:
    assert client.post(
        "/api/users/register",
        json={"username": "alice", "password": "secret1"},
    ).status_code == 200
    assert client.post(
        "/api/users/login",
        json={"username": "alice", "password": "secret1"},
    ).status_code == 200


def _login_admin(client: TestClient) -> None:
    assert client.post(
        "/api/users/login",
        json={"username": "admin", "password": "admintestpassword"},
    ).status_code == 200


def test_empty_problem_list(problem_client: tuple[TestClient, Path]) -> None:
    client, _ = problem_client
    _register_and_login(client)

    response = client.get("/api/problems/")

    assert response.status_code == 200
    assert response.json() == {"code": 200, "msg": "success", "data": []}


def test_create_list_and_get_problem(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, problems_path = problem_client
    _register_and_login(client)

    created = client.post("/api/problems/", json=problem_data)
    listing = client.get("/api/problems/")
    detail = client.get("/api/problems/P1001")

    assert created.status_code == 200
    assert created.json() == {"code": 200, "msg": "add success", "data": {"id": "P1001"}}
    assert listing.json() == {
        "code": 200,
        "msg": "success",
        "data": [{"id": "P1001", "title": "A+B Problem"}],
    }
    assert detail.status_code == 200
    assert detail.json() == {"code": 200, "msg": "success", "data": problem_data}
    assert json.loads((problems_path / "P1001.json").read_text(encoding="utf-8")) == problem_data


def test_optional_fields_use_documented_defaults(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, _ = problem_client
    _register_and_login(client)
    for optional in (
        "hint",
        "source",
        "tags",
        "time_limit",
        "memory_limit",
        "author",
        "difficulty",
    ):
        problem_data.pop(optional)

    assert client.post("/api/problems/", json=problem_data).status_code == 200
    data = client.get("/api/problems/P1001").json()["data"]

    assert data | {} == {
        **problem_data,
        "hint": "",
        "source": "",
        "tags": [],
        "time_limit": 3.0,
        "memory_limit": 128,
        "author": "",
        "difficulty": "",
    }


def test_list_is_sorted_by_problem_id(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, _ = problem_client
    _register_and_login(client)
    for problem_id in ("Z9", "A2", "A1"):
        payload = {**problem_data, "id": problem_id, "title": problem_id}
        assert client.post("/api/problems/", json=payload).status_code == 200

    response = client.get("/api/problems/")

    assert [item["id"] for item in response.json()["data"]] == ["A1", "A2", "Z9"]


def test_update_is_fully_validated_and_persisted(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, problems_path = problem_client
    _register_and_login(client)
    assert client.post("/api/problems/", json=problem_data).status_code == 200
    updated = {**problem_data, "title": "Updated title", "time_limit": 2.5}

    response = client.put("/api/problems/P1001", json=updated)

    assert response.json() == {
        "code": 200,
        "msg": "update success",
        "data": {"id": "P1001"},
    }
    stored = json.loads((problems_path / "P1001.json").read_text(encoding="utf-8"))
    assert stored == updated


def test_incomplete_update_does_not_damage_original(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, problems_path = problem_client
    _register_and_login(client)
    assert client.post("/api/problems/", json=problem_data).status_code == 200
    original = (problems_path / "P1001.json").read_bytes()
    incomplete = {**problem_data}
    incomplete.pop("title")

    response = client.put("/api/problems/P1001", json=incomplete)

    assert response.status_code == 400
    assert (problems_path / "P1001.json").read_bytes() == original


def test_update_rejects_body_id_mismatch(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, _ = problem_client
    _register_and_login(client)
    assert client.post("/api/problems/", json=problem_data).status_code == 200

    response = client.put("/api/problems/P1001", json={**problem_data, "id": "P1002"})

    assert response.status_code == 400
    assert response.json()["code"] == 400


@pytest.mark.parametrize(
    "missing_field",
    [
        "id",
        "title",
        "description",
        "input_description",
        "output_description",
        "samples",
        "constraints",
        "testcases",
    ],
)
def test_missing_required_field_returns_400(
    problem_client: tuple[TestClient, Path],
    problem_data: dict[str, object],
    missing_field: str,
) -> None:
    client, _ = problem_client
    _register_and_login(client)
    problem_data.pop(missing_field)

    response = client.post("/api/problems/", json=problem_data)

    assert response.status_code == 400
    assert response.json()["code"] == 400


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("samples", []),
        ("samples", "not-a-list"),
        ("samples", [{}]),
        ("samples", [{"input": "1"}]),
        ("samples", [{"input": 1, "output": "1"}]),
        ("testcases", []),
        ("testcases", "not-a-list"),
        ("testcases", [{}]),
        ("testcases", [{"input": "1", "output": None}]),
    ],
)
def test_invalid_nested_list_structure_returns_400(
    problem_client: tuple[TestClient, Path],
    problem_data: dict[str, object],
    field: str,
    invalid_value: object,
) -> None:
    client, _ = problem_client
    _register_and_login(client)

    response = client.post("/api/problems/", json={**problem_data, field: invalid_value})

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("time_limit", 0),
        ("time_limit", -0.1),
        ("time_limit", "1.0"),
        ("time_limit", None),
        ("memory_limit", 0),
        ("memory_limit", -1),
        ("memory_limit", 1.5),
        ("memory_limit", "128"),
        ("memory_limit", None),
    ],
)
def test_invalid_resource_limits_return_400(
    problem_client: tuple[TestClient, Path],
    problem_data: dict[str, object],
    field: str,
    invalid_value: object,
) -> None:
    client, _ = problem_client
    _register_and_login(client)

    response = client.post("/api/problems/", json={**problem_data, field: invalid_value})

    assert response.status_code == 400


def test_duplicate_problem_id_returns_409(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, _ = problem_client
    _register_and_login(client)
    assert client.post("/api/problems/", json=problem_data).status_code == 200

    response = client.post("/api/problems/", json=problem_data)

    assert response.status_code == 409
    assert response.json()["code"] == 409


def test_missing_problem_returns_404(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, _ = problem_client
    _register_and_login(client)

    assert client.get("/api/problems/missing").status_code == 404
    update = client.put("/api/problems/missing", json={**problem_data, "id": "missing"})
    assert update.status_code == 404
    _login_admin(client)
    assert client.delete("/api/problems/missing").status_code == 404


@pytest.mark.parametrize(
    "problem_id",
    ["..", "../escape", "/absolute", "a/b", "a\\b", "C:\\evil", "bad.id"],
)
def test_repository_rejects_unsafe_problem_ids(problem_id: str) -> None:
    with pytest.raises(ValueError, match="invalid problem id"):
        validate_problem_id(problem_id)


@pytest.mark.parametrize(
    "problem_id",
    ["..", "../escape", "/absolute", "a/b", "a\\b", "C:\\evil", "bad.id"],
)
def test_create_rejects_unsafe_problem_ids(
    problem_client: tuple[TestClient, Path],
    problem_data: dict[str, object],
    problem_id: str,
) -> None:
    client, problems_path = problem_client
    _register_and_login(client)

    response = client.post("/api/problems/", json={**problem_data, "id": problem_id})

    assert response.status_code == 400
    assert list(problems_path.glob("*.json")) == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/problems/"),
        ("get", "/api/problems/P1001"),
        ("post", "/api/problems/"),
        ("put", "/api/problems/P1001"),
        ("delete", "/api/problems/P1001"),
    ],
)
def test_all_problem_operations_require_login(
    problem_client: tuple[TestClient, Path], method: str, path: str
) -> None:
    client, _ = problem_client

    response = client.request(method, path)

    assert response.status_code == 401
    assert response.json()["code"] == 401


def test_regular_user_cannot_delete_problem(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, problems_path = problem_client
    _register_and_login(client)
    assert client.post("/api/problems/", json=problem_data).status_code == 200

    response = client.delete("/api/problems/P1001")

    assert response.status_code == 403
    assert (problems_path / "P1001.json").is_file()


def test_admin_can_delete_problem(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, problems_path = problem_client
    _register_and_login(client)
    assert client.post("/api/problems/", json=problem_data).status_code == 200
    _login_admin(client)

    response = client.delete("/api/problems/P1001")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "msg": "delete success",
        "data": {"id": "P1001"},
    }
    assert not (problems_path / "P1001.json").exists()


def test_validation_is_400_instead_of_422(
    problem_client: tuple[TestClient, Path], problem_data: dict[str, object]
) -> None:
    client, _ = problem_client
    _register_and_login(client)

    malformed_json = client.post(
        "/api/problems/",
        content="{",
        headers={"content-type": "application/json"},
    )
    wrong_type = client.post("/api/problems/", json={**problem_data, "memory_limit": "128"})

    assert malformed_json.status_code == 400
    assert wrong_type.status_code == 400
    assert malformed_json.json()["code"] == wrong_type.json()["code"] == 400


def test_problem_survives_application_restart(
    tmp_path: Path, problem_data: dict[str, object]
) -> None:
    settings = Settings(
        database_path=tmp_path / "persistent.sqlite3",
        problems_path=tmp_path / "problems",
        environment="test",
    )
    with TestClient(create_app(settings)) as first_client:
        _register_and_login(first_client)
        assert first_client.post("/api/problems/", json=problem_data).status_code == 200

    with TestClient(create_app(settings)) as restarted_client:
        assert restarted_client.post(
            "/api/users/login",
            json={"username": "alice", "password": "secret1"},
        ).status_code == 200
        response = restarted_client.get("/api/problems/P1001")

    assert response.status_code == 200
    assert response.json()["data"] == problem_data


def test_problem_route_handlers_are_async() -> None:
    endpoints = [route.endpoint for route in problems_router.routes if hasattr(route, "endpoint")]

    assert len(endpoints) == 5
    assert all(inspect.iscoroutinefunction(endpoint) for endpoint in endpoints)
