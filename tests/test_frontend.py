"""Frontend API, state, conversion, navigation, and smoke tests."""

import json
import re
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from frontend.api_client import ApiClient
from frontend.components import ui
from frontend.components.pagination import page_count
from frontend.components.theme import GLOBAL_CSS
from frontend.data_access import (
    load_language_names,
    load_problem_summaries,
    load_submission_options,
)
from frontend.errors import ApiError, NetworkError, ProtocolError
from frontend.models import (
    NAVIGATION_LAYOUT,
    NAVIGATION_METADATA,
    build_problem_payload,
    navigation_for,
    navigation_sections,
    should_poll,
    status_text,
    validate_login,
    validate_problem,
    validate_registration,
)
from frontend.pages import agent as agent_page
from frontend.pages import auth as auth_page
from frontend.session import (
    auth_resolution_pending,
    browser_bridge_base_url,
    clear_auth,
    current_user,
    get_api_client,
    logout_local,
    prepare_browser_bridge,
    restore_identity,
    set_auth_user,
    sync_browser_auth,
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


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "填写内容有误，请检查后重试。"),
        (404, "没有找到相关内容。"),
        (409, "当前操作存在冲突，请刷新后重试。"),
        (429, "操作过于频繁，请稍后再试。"),
        (500, "服务暂时不可用，请稍后重试。"),
    ],
)
def test_http_errors_hide_technical_backend_message(status: int, expected: str) -> None:
    client = ApiClient(
        "http://test/api",
        transport=httpx.MockTransport(lambda _: envelope(status, msg="specific message")),
    )
    with pytest.raises(ApiError) as caught:
        client.get("/failure")
    assert caught.value.status_code == status
    assert caught.value.user_message == expected
    assert "specific message" not in caught.value.user_message


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"type": "missing", "loc": ["body", "password"], "msg": "Field required"}, "请输入密码。"),
        (
            {"type": "string_too_long", "loc": ["body", "title"], "msg": "too long"},
            "标题内容过长，请适当精简。",
        ),
        (
            {"type": "int_parsing", "loc": ["query", "user_id"], "msg": "bad int"},
            "用户 ID 格式不正确，请填写有效数字。",
        ),
    ],
)
def test_validation_errors_are_translated_by_field(error: dict[str, Any], expected: str) -> None:
    exc = ApiError(400, "Invalid request data", [error])
    assert exc.user_message == expected
    assert "Invalid" not in exc.user_message


def test_known_backend_messages_are_translated() -> None:
    assert ApiError(401, "Invalid username or password").user_message == (
        "用户名或密码错误，请重新输入。"
    )
    assert ApiError(403, "Permission denied").user_message == "你没有权限执行此操作。"
    assert ApiError(400, "Username already exists").user_message == (
        "该用户名已被使用，请换一个试试。"
    )


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
    assert validate_registration("", "", "") == [
        "请输入用户名。",
        "请输入密码。",
        "请再次输入密码。",
    ]
    assert validate_login("", "") == ["请输入用户名。", "请输入密码。"]
    assert validate_login("ab", "secret1") == ["用户不存在。"]


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


def test_new_streamlit_session_does_not_share_server_side_cookie_jar() -> None:
    first_state: dict[str, Any] = {}
    refreshed_state: dict[str, Any] = {}

    first = get_api_client(first_state)
    first._client.cookies.set("session_id", "secret")
    refreshed = get_api_client(refreshed_state)

    assert refreshed is not first
    assert not refreshed.has_cookies

    logout_local(first, first_state)
    logout_local(refreshed, refreshed_state)


def test_confirmed_identity_skips_bridge_and_users_me_on_ordinary_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return envelope(data={})

    state: dict[str, Any] = {"auth_user": {"id": 1, "role": "user"}}
    client = ApiClient("http://identity-test/api", transport=httpx.MockTransport(handler))
    client._client.cookies.set("session_id", "server-only")
    monkeypatch.setattr(
        "frontend.session.mount_auth_bridge",
        lambda **_: pytest.fail("confirmed sessions must not rebuild the browser bridge"),
    )

    assert sync_browser_auth(client, state) == {"id": 1, "role": "user"}
    assert requests == []


@pytest.mark.parametrize(
    ("api_url", "browser_host", "expected"),
    [
        (
            "http://localhost:8000/api",
            "127.0.0.1:8501",
            "http://127.0.0.1:8000/api",
        ),
        (
            "http://127.0.0.1:8000/api",
            "localhost:8501",
            "http://localhost:8000/api",
        ),
        (
            "https://api.example.com/api",
            "localhost:8501",
            "https://api.example.com/api",
        ),
    ],
)
def test_browser_bridge_uses_same_loopback_hostname(
    api_url: str, browser_host: str, expected: str
) -> None:
    assert browser_bridge_base_url(api_url, browser_host) == expected


def test_initial_browser_auth_resolution_hides_anonymous_navigation() -> None:
    client = ApiClient(
        "http://auth-gate-test/api", transport=httpx.MockTransport(lambda _: envelope())
    )

    assert auth_resolution_pending(client, {}) is True
    assert auth_resolution_pending(client, {"auth_bridge_attempted": True}) is False
    assert (
        auth_resolution_pending(
            client,
            {"auth_bridge_action": "clear", "auth_bridge_attempted": False},
        )
        is False
    )

    client._client.cookies.set("session_id", "server-only")
    assert auth_resolution_pending(client, {}) is False
    assert auth_resolution_pending(client, {"auth_user": {"id": 1}}) is False


def test_reference_resources_are_requested_once_across_page_navigation() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/problems/"):
            return envelope(
                data=[
                    {
                        "id": "P1",
                        "title": "Sum",
                        "difficulty": "easy",
                        "tags": ["math"],
                        "source": "course",
                        "author": "teacher",
                        "testcases": [{"input": "secret", "output": "secret"}],
                    }
                ]
            )
        return envelope(data={"name": ["python", "cpp"]})

    load_problem_summaries.clear()
    load_language_names.clear()
    client = ApiClient("http://reference-cache-test/api", transport=httpx.MockTransport(handler))

    problem_page_data = load_problem_summaries(client.base_url, client)
    first_submit_options = load_submission_options(client)
    second_submit_options = load_submission_options(client)

    assert problem_page_data == first_submit_options[0] == second_submit_options[0]
    assert "testcases" not in problem_page_data[0]
    assert first_submit_options[1] == second_submit_options[1] == ["python", "cpp"]
    assert calls.count("/api/problems/") == 1
    assert calls.count("/api/languages/") == 1


@pytest.mark.parametrize(
    ("total", "page_size", "expected"),
    [(0, 10, 1), (1, 10, 1), (10, 10, 1), (11, 10, 2), (101, 50, 3)],
)
def test_compact_pagination_page_count(
    total: int, page_size: int, expected: int
) -> None:
    assert page_count(total, page_size) == expected


def test_paginated_pages_share_compact_table_footer() -> None:
    frontend = Path(__file__).parents[1] / "frontend"
    auth_source = (frontend / "pages" / "auth.py").read_text(encoding="utf-8")
    submission_source = (frontend / "pages" / "submissions.py").read_text(
        encoding="utf-8"
    )

    assert 'render_pagination("user_admin", total=total)' in auth_source
    assert 'render_pagination("submission_list", total=' in submission_source
    assert 'number_input("页码"' not in auth_source + submission_source


def test_agent_renders_only_selected_view(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered: list[str] = []
    monkeypatch.setattr(agent_page, "page_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(agent_page, "badges", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        agent_page.st,
        "segmented_control",
        lambda *_args, **_kwargs: "创建任务",
    )
    monkeypatch.setattr(agent_page, "_config", lambda _api: rendered.append("config"))
    monkeypatch.setattr(
        agent_page, "_authoring_form", lambda _api: rendered.append("authoring")
    )
    monkeypatch.setattr(agent_page, "_task_monitor", lambda _api: rendered.append("tasks"))

    agent_page.render_agent(object())  # type: ignore[arg-type]

    assert rendered == ["authoring"]


def test_bridge_ticket_restores_cookie_then_authoritative_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/exchange"):
            return httpx.Response(
                200,
                headers={"set-cookie": "session_id=restored; HttpOnly; Path=/"},
                json={"code": 200, "msg": "session restored", "data": None},
            )
        return envelope(data={"id": 7, "username": "alice", "role": "admin"})

    state: dict[str, Any] = {"auth_bridge_nonce": "nonce-a"}
    monkeypatch.setattr(
        "frontend.session.mount_auth_bridge",
        lambda **_: SimpleNamespace(ticket="one-use-ticket", ticket_nonce="nonce-a"),
    )
    client = ApiClient("http://test/api", transport=httpx.MockTransport(handler))

    user = sync_browser_auth(client, state)

    assert user == {"id": 7, "username": "alice", "role": "admin"}
    assert current_user(state) == user
    assert calls == ["/api/auth/bridge/exchange", "/api/users/me"]


def test_prepare_bridge_keeps_claim_ephemeral_in_streamlit_state() -> None:
    state: dict[str, Any] = {}
    client = ApiClient(
        "http://test/api",
        transport=httpx.MockTransport(
            lambda _: envelope(data={"token": "opaque-browser-recovery-token"})
        ),
    )

    prepare_browser_bridge(client, state)

    assert state["auth_bridge_action"] == "claim"
    assert state["auth_bridge_claim"] == "opaque-browser-recovery-token"
    assert "session_id" not in repr(state)


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
    assert "题目列表" not in anonymous
    assert "提交代码" in regular and "用户管理" not in regular
    assert "AI 智能命题" in regular
    assert {"用户管理", "日志可见性"} <= set(admin)


def test_navigation_is_grouped_with_unique_paths_and_icons() -> None:
    configured_pages = [page for pages in NAVIGATION_LAYOUT.values() for page in pages]
    assert set(configured_pages) == set(NAVIGATION_METADATA)
    assert len(configured_pages) == len(set(configured_pages))
    paths = [metadata["url_path"] for metadata in NAVIGATION_METADATA.values()]
    assert len(paths) == len(set(paths))
    assert all(
        metadata["icon"].startswith(":material/") for metadata in NAVIGATION_METADATA.values()
    )

    assert navigation_sections(None) == {
        "概览": ["首页"],
        "账户": ["注册", "登录"],
    }
    assert navigation_sections("user")["题目"][-1] == "AI 智能命题"
    assert navigation_sections("user")["评测"] == ["提交代码", "提交记录"]
    assert navigation_sections("admin")["题目"][-1] == "AI 智能命题"
    assert navigation_sections("admin")["评测"][-1] == "日志可见性"


def test_login_and_logout_use_navigation_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubApi:
        def post(self, path: str, **_: Any) -> None:
            calls.append(path)

    calls: list[str] = []
    transitions: list[str] = []
    headers: list[str] = []
    inputs = iter(["alice", "secret1"])
    monkeypatch.setattr(auth_page.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page.st, "form", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(auth_page.st, "text_input", lambda *_args, **_kwargs: next(inputs))
    monkeypatch.setattr(auth_page.st, "form_submit_button", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(auth_page.st, "success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page.st, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page.st, "button", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        auth_page,
        "page_header",
        lambda title, *_args, **_kwargs: headers.append(title),
    )
    monkeypatch.setattr(auth_page, "restore_identity", lambda _api: {"id": 1, "role": "user"})
    monkeypatch.setattr(auth_page, "prepare_browser_bridge", lambda _api: None)
    monkeypatch.setattr(auth_page, "set_auth_user", lambda _user: None)
    monkeypatch.setattr(auth_page, "logout_local", lambda _api: transitions.append("cleared"))
    monkeypatch.setattr(
        auth_page.st,
        "rerun",
        lambda: pytest.fail("navigation callback should replace a plain rerun"),
    )

    auth_page.render_login(StubApi(), lambda: transitions.append("login-home"))
    auth_page.render_logout(StubApi(), lambda: transitions.append("logout-home"))

    assert calls == ["/auth/login", "/auth/logout"]
    assert transitions == ["login-home", "cleared", "logout-home"]
    assert headers[:2] == ["欢迎回来", "正在登录"]


def test_registration_logs_in_and_uses_navigation_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubApi:
        def post(self, path: str, **kwargs: Any) -> None:
            calls.append((path, kwargs.get("json")))

    calls: list[tuple[str, Any]] = []
    transitions: list[str] = []
    inputs = iter(["alice", "secret1", "secret1"])
    monkeypatch.setattr(auth_page, "page_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page, "section_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page.st, "form", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(auth_page.st, "text_input", lambda *_args, **_kwargs: next(inputs))
    monkeypatch.setattr(auth_page.st, "form_submit_button", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(auth_page.st, "success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        auth_page,
        "restore_identity",
        lambda _api: {"id": 1, "username": "alice", "role": "user"},
    )
    monkeypatch.setattr(auth_page, "prepare_browser_bridge", lambda _api: None)
    monkeypatch.setattr(
        auth_page,
        "set_auth_user",
        lambda user: transitions.append(f"authenticated:{user['username']}"),
    )
    monkeypatch.setattr(
        auth_page.st,
        "rerun",
        lambda: pytest.fail("navigation callback should replace a plain rerun"),
    )

    auth_page.render_register(StubApi(), lambda: transitions.append("register-home"))

    credentials = {"username": "alice", "password": "secret1"}
    assert calls == [("/users/", credentials), ("/auth/login", credentials)]
    assert transitions == ["authenticated:alice", "register-home"]


def test_empty_login_is_rejected_before_api_request(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailApi:
        def post(self, *_args: Any, **_kwargs: Any) -> None:
            pytest.fail("empty login must not call the API")

    messages: list[str] = []
    inputs = iter(["", ""])
    monkeypatch.setattr(auth_page, "page_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page, "section_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page.st, "form", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(auth_page.st, "text_input", lambda *_args, **_kwargs: next(inputs))
    monkeypatch.setattr(auth_page.st, "form_submit_button", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(auth_page.st, "error", lambda message, **_kwargs: messages.append(message))

    auth_page.render_login(FailApi())

    assert messages == ["请输入用户名。", "请输入密码。"]


def test_admin_profile_uses_admin_identity_header(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubApi:
        def get(self, _path: str) -> dict[str, Any]:
            return {
                "data": {
                    "username": "root",
                    "role": "admin",
                    "join_time": "2026-09-03",
                    "submit_count": 0,
                    "resolve_count": 0,
                }
            }

    class Column:
        def __enter__(self) -> "Column":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def metric(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    headers: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        auth_page,
        "page_header",
        lambda title, _subtitle, **kwargs: headers.append((title, kwargs)),
    )
    monkeypatch.setattr(auth_page, "badges", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page, "info_card", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page, "section_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_page.st, "columns", lambda count: [Column() for _ in range(count)])

    auth_page.render_profile(StubApi(), {"id": 1})

    assert headers == [("管理员中心", {"icon": "🛡️", "eyebrow": "ADMIN ACCOUNT"})]


def test_problem_operation_radio_hides_redundant_label() -> None:
    frontend = Path(__file__).parents[1] / "frontend"
    source = (frontend / "pages" / "problems.py").read_text(encoding="utf-8")
    assert 'section_header("操作", icon="🎛️")' in source
    assert 'label_visibility="collapsed"' in source
    assert "选择操作" not in source


def test_submission_state_and_accessible_labels() -> None:
    assert should_poll("pending")
    assert not should_poll("success")
    assert not should_poll("error")
    assert status_text("AC") == "答案正确（AC）"
    assert status_text("TLE") == "时间超限（TLE）"


def test_visual_theme_has_required_tokens_and_accessibility_rules() -> None:
    normalized = GLOBAL_CSS.lower()
    assert "#5b5cf0" in normalized
    assert "#06b6d4" in normalized
    assert "#f97316" in normalized
    assert "pingfang sc" in normalized
    assert "prefers-reduced-motion" in normalized
    assert "focus-visible" in normalized
    assert "max-width: 600px" in normalized
    assert ".oj-section-title h2" in normalized
    assert "padding: 0 !important" in normalized
    assert "align-items: center" in normalized
    assert '[data-baseweb="tab-highlight"]' in normalized
    assert '[data-baseweb="tab-border"]' in normalized
    assert "background: transparent !important" in normalized
    assert "border-left: 4px solid var(--oj-primary)" not in normalized
    assert '[data-testid="stheaderactionelements"]' in normalized
    assert "input::placeholder" in normalized
    assert "font-style: italic" in normalized


def test_visual_components_escape_dynamic_html(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered: list[tuple[str, bool]] = []

    def capture(body: str, *, unsafe_allow_html: bool = False) -> None:
        rendered.append((body, unsafe_allow_html))

    monkeypatch.setattr(ui.st, "markdown", capture)
    ui.page_header("<script>alert(1)</script>", '"unsafe"', icon="<")
    ui.timeline_event("<time>", "stage", "<img src=x onerror=alert(1)>")
    ui.feature_grid([("<", "第一项", "安全描述"), ("②", "第二项", "<script>unsafe</script>")])

    combined = "".join(body for body, _ in rendered)
    assert "<script>" not in combined
    assert "<img src=" not in combined
    assert "&lt;script&gt;" in combined
    assert "&lt;img src=x onerror=alert(1)&gt;" in combined
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in combined
    assert not re.search(r"\n[ \t]{4,}<article", rendered[-1][0])
    assert all(unsafe for _, unsafe in rendered)


def test_user_facing_pages_have_no_manual_required_asterisks_or_technical_copy() -> None:
    frontend = Path(__file__).parents[1] / "frontend"
    page_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [frontend / "app.py", *(frontend / "pages").glob("*.py")]
    )
    assert not re.search(r'("|f")[^"\n]* \*"', page_sources)
    for phrase in ("Invalid request data", "课程 API", "FastAPI", "后端", "Session", "Cookie"):
        assert phrase not in page_sources
    for redundant_copy in ("选择新增、编辑或删除题目", "输入用户名和密码，继续你的训练"):
        assert redundant_copy not in page_sources


def test_agent_currency_uses_common_and_custom_options() -> None:
    assert agent_page.COMMON_CURRENCIES == ["CNY", "USD", "EUR", "GBP", "JPY", "HKD"]
    source = Path(agent_page.__file__).read_text(encoding="utf-8")
    assert "accept_new_options=True" in source


def test_agent_problem_type_uses_common_and_custom_options() -> None:
    assert agent_page.PROBLEM_TYPES == [
        "基础编程",
        "算法设计",
        "数据结构",
        "数学",
        "字符串",
        "图论",
        "动态规划",
    ]
    source = Path(agent_page.__file__).read_text(encoding="utf-8")
    assert 'with st.expander("高级设置（选填）")' in source
    assert '"期望算法或复杂度",\n                placeholder=OPTIONAL_PLACEHOLDER' in source


def test_status_badges_use_distinct_accessible_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered: list[str] = []
    monkeypatch.setattr(
        ui.st,
        "markdown",
        lambda body, **_kwargs: rendered.append(body),
    )
    for status in ("pending", "success", "error"):
        ui.status_badge(status)
    assert "oj-badge--orange" in rendered[0] and "oj-badge--pending" in rendered[0]
    assert "oj-badge--green" in rendered[1]
    assert "oj-badge--red" in rendered[2]
    statuses = ("pending", "success", "error")
    assert all(status in body for status, body in zip(statuses, rendered, strict=True))


def test_streamlit_application_smoke() -> None:
    testing = pytest.importorskip("streamlit.testing.v1")
    app_path = Path(__file__).parents[1] / "frontend" / "app.py"
    loading_app = testing.AppTest.from_file(app_path, default_timeout=10).run()
    assert not loading_app.exception
    assert any("正在载入" in item.value for item in loading_app.markdown)
    assert not any("当前状态：未登录" in item.value for item in loading_app.caption)

    app = testing.AppTest.from_file(app_path, default_timeout=10)
    app.session_state["auth_bridge_attempted"] = True
    app.run()
    assert not app.exception
    assert any("Programming Training OJ" in item.value for item in app.markdown)
    assert any("oj-feature-grid" in item.value for item in app.markdown)
    assert not any("<article" in item.value for item in app.code)
    assert len(app.selectbox) == 0
