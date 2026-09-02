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


def test_only_health_endpoint_is_exposed() -> None:
    paths = set(app.openapi()["paths"])
    assert paths == {"/api/health"}
