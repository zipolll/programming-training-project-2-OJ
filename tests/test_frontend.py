"""Frontend API, state, conversion, navigation, and smoke tests."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from frontend.api_client import ApiClient
from frontend.errors import ApiError, NetworkError, ProtocolError
from frontend.models import (
    build_problem_payload,
    navigation_for,
    should_poll,
    status_text,
    validate_problem,
    validate_registration,
)
from frontend.session import (
    clear_auth,
    current_user,
    logout_local,
    restore_identity,
    set_auth_user,
)


def envelope(status: int = 200, data: Any = None, msg: str = "success") -> httpx.Response:
    return httpx.Response(status, json={"code": status, "msg": msg, "data": data})


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("GET", lambda client: client.get("/items", params={"page": 2})),
        ("POST", lambda client: client.post("/items", json={"name": "x"})),
        ("PUT", lambda client: client.put("/items/1", json={"name": "y"})),
        ("DELETE", lambda client: client.delete("/items/1")),
    ],
)
def test_api_client_methods_query_and_json(method: str, call: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == method
        if method == "GET":
            assert request.url.params["page"] == "2"
        elif method != "DELETE":
            assert json.loads(request.content) in ({"name": "x"}, {"name": "y"})
        return envelope(data={"ok": True})

    client = ApiClient("http://test/api", transport=httpx.MockTransport(handler))
    assert call(client)["data"] == {"ok": True}


def test_cookie_is_saved_sent_and_cleared_on_401() -> None:
    calls = 0
    unauthorized = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"set-cookie": "session_id=secret; HttpOnly; Path=/"},
                json={"code": 200, "msg": "success", "data": {}},
            )
        assert "session_id=secret" in request.headers["cookie"]
        return envelope(401, msg="login required")

    client = ApiClient(
        "http://test/api",
        transport=httpx.MockTransport(handler),
        on_unauthorized=lambda: unauthorized.append(True),
    )
    client.post("/login")
    assert client.has_cookies
    with pytest.raises(ApiError, match="login required"):
        client.get("/me")
    assert not client.has_cookies
    assert unauthorized == [True]


def test_403_preserves_cookie_and_identity_callback() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return envelope(403, msg="Permission denied")

    callback = []
    client = ApiClient(
        "http://test/api",
        transport=httpx.MockTransport(handler),
        on_unauthorized=lambda: callback.append(True),
    )
    client._client.cookies.set("session_id", "secret")
    with pytest.raises(ApiError) as caught:
        client.get("/admin")
    assert caught.value.status_code == 403
    assert client.has_cookies
    assert callback == []


@pytest.mark.parametrize("status", [400, 404, 409, 429, 500])
def test_http_errors_keep_backend_message(status: int) -> None:
    client = ApiClient(
        "http://test/api",
        transport=httpx.MockTransport(lambda _: envelope(status, msg="specific message")),
    )
    with pytest.raises(ApiError) as caught:
        client.get("/failure")
    assert caught.value.status_code == status
    assert "specific message" in caught.value.user_message


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"code": 200, "msg": "success"}),
        httpx.Response(200, json={"code": "200", "msg": "success", "data": None}),
        httpx.Response(200, json={"code": 201, "msg": "success", "data": None}),
        httpx.Response(200, json=[200, "success", None]),
    ],
)
def test_invalid_api_responses(response: httpx.Response) -> None:
    client = ApiClient("http://test/api", transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(ProtocolError):
        client.get("/broken")


@pytest.mark.parametrize(
    ("error", "timeout"),
    [
        (httpx.ReadTimeout("slow"), True),
        (httpx.ConnectError("offline"), False),
    ],
)
def test_network_failures_are_safe(error: Exception, timeout: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        error.request = request  # type: ignore[attr-defined]
        raise error

    client = ApiClient("http://test/api", transport=httpx.MockTransport(handler))
    with pytest.raises(NetworkError) as caught:
        client.get("/network")
    assert caught.value.is_timeout is timeout
    assert "secret" not in caught.value.user_message


def test_registration_validation() -> None:
    assert validate_registration("ab", "123", "456") == [
        "用户名长度应为 3–40 个字符。",
        "密码至少需要 6 个字符。",
        "两次输入的密码不一致。",
    ]
    assert validate_registration("alice", "secret1", "secret1") == []


def test_problem_payload_multiple_samples_and_testcases() -> None:
    values = {
        "id": " P1 ",
        "title": " Sum ",
        "description": "Add",
        "input_description": "ints",
        "output_description": "sum",
        "constraints": "small",
        "samples": [{"input": "1 2", "output": "3"}, {"input": "0 0", "output": "0"}],
        "testcases": [{"input": "2 3", "output": "5"}, {"input": "-1 1", "output": "0"}],
        "tags": [" math ", ""],
        "time_limit": 1,
        "memory_limit": 64,
    }
    payload = build_problem_payload(values)
    assert payload["id"] == "P1"
    assert payload["title"] == "Sum"
    assert len(payload["samples"]) == len(payload["testcases"]) == 2
    assert payload["tags"] == ["math"]
    assert validate_problem(payload) == []


def test_problem_validation_rejects_invalid_complete_form() -> None:
    payload = build_problem_payload({"id": "../bad", "time_limit": 0, "memory_limit": 0})
    errors = validate_problem(payload)
    assert len(errors) == 10
    assert any("题目 ID" in item for item in errors)


def test_auth_state_is_explicit_and_logout_clears_cookie() -> None:
    state: dict[str, Any] = {}
    set_auth_user({"id": 1, "role": "user"}, state)
    assert current_user(state) == {"id": 1, "role": "user"}
    clear_auth(state)
    assert current_user(state) is None
    client = ApiClient("http://test/api", transport=httpx.MockTransport(lambda _: envelope()))
    client._client.cookies.set("session_id", "secret")
    logout_local(client, state)
    assert not client.has_cookies
    assert current_user(state) is None


def test_login_cookie_restores_authoritative_identity() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"set-cookie": "session_id=secret; HttpOnly; Path=/"},
                json={"code": 200, "msg": "login success", "data": {"role": "wrong"}},
            )
        assert request.url.path == "/api/users/me"
        return envelope(data={"id": 7, "username": "alice", "role": "admin"})

    state: dict[str, Any] = {}
    client = ApiClient("http://test/api", transport=httpx.MockTransport(handler))
    client.post("/auth/login", json={"username": "alice", "password": "secret1"})
    user = restore_identity(client, state)
    assert user == {"id": 7, "username": "alice", "role": "admin"}
    assert current_user(state) == user


def test_banned_identity_is_cleared_but_generic_403_is_not() -> None:
    state: dict[str, Any] = {"auth_user": {"id": 7, "role": "user"}}
    client = ApiClient(
        "http://test/api",
        transport=httpx.MockTransport(lambda _: envelope(403, msg="User is banned")),
    )
    client._client.cookies.set("session_id", "secret")
    with pytest.raises(ApiError):
        restore_identity(client, state)
    assert current_user(state) is None
    assert not client.has_cookies


def test_identity_cannot_be_restored_without_backend_cookie() -> None:
    state: dict[str, Any] = {"auth_user": {"id": 1, "role": "admin"}}
    client = ApiClient("http://test/api", transport=httpx.MockTransport(lambda _: envelope()))
    assert restore_identity(client, state) is None
    assert current_user(state) is None


def test_navigation_is_role_aware() -> None:
    anonymous = navigation_for(None)
    regular = navigation_for("user")
    admin = navigation_for("admin")
    assert "登录" in anonymous and "提交代码" not in anonymous
    assert "提交代码" in regular and "用户管理" not in regular
    assert {"用户管理", "日志可见性"} <= set(admin)


def test_submission_state_and_accessible_labels() -> None:
    assert should_poll("pending")
    assert not should_poll("success")
    assert not should_poll("error")
    assert status_text("AC") == "答案正确（AC）"
    assert status_text("TLE") == "时间超限（TLE）"


def test_streamlit_application_smoke() -> None:
    testing = pytest.importorskip("streamlit.testing.v1")
    app_path = Path(__file__).parents[1] / "frontend" / "app.py"
    app = testing.AppTest.from_file(app_path, default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "Programming Training OJ"
    assert app.selectbox[0].options == navigation_for(None)
