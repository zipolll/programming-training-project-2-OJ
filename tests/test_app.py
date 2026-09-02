"""Application skeleton tests."""

from fastapi.testclient import TestClient

from backend.app.main import app, create_app


def test_application_factory() -> None:
    application = create_app()
    assert application.title == "Programming Training OJ"


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "msg": "success",
        "data": {"status": "ok"},
    }


def test_expected_first_stage_endpoints_are_exposed() -> None:
    paths = set(app.openapi()["paths"])
    assert paths == {
        "/api/health",
        "/api/users/register",
        "/api/users/login",
        "/api/users/logout",
        "/api/users/me",
    }
