"""Application skeleton tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import app, create_app


def test_application_factory() -> None:
    application = create_app()
    assert application.title == "Programming Training OJ"


def test_health_check(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "oj.sqlite3",
        problems_path=tmp_path / "problems",
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "msg": "success",
        "data": {"status": "ok"},
    }


def test_expected_first_stage_endpoints_are_exposed() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/languages/",
        "/api/logs/access/",
        "/api/logs/audit/",
        "/api/problems/",
        "/api/problems/{problem_id}",
        "/api/problems/{problem_id}/log_visibility",
        "/api/submissions/",
        "/api/submissions/{submission_id}",
        "/api/submissions/{submission_id}/log",
        "/api/submissions/{submission_id}/rejudge",
        "/api/users/",
        "/api/users/admin",
        "/api/users/register",
        "/api/users/login",
        "/api/users/logout",
        "/api/users/me",
        "/api/users/{user_id}",
        "/api/users/{user_id}/role",
    } <= paths
