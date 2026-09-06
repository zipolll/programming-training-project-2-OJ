"""Registration, login, profile, logout, and user administration pages."""

from collections.abc import Callable

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import REQUIRED_PLACEHOLDER, show_error
from frontend.components.layout import cell_text, data_table, section_card, table_row
from frontend.components.pagination import pagination_values, render_pagination
from frontend.components.ui import badges, info_card, list_count, page_header, section_header
from frontend.errors import ApiError
from frontend.models import validate_login, validate_registration
from frontend.session import (
    logout_local,
    prepare_browser_bridge,
    restore_identity,
    set_auth_user,
)
from frontend.session_cache import cached_for_session, clear_session_cache


def render_register(api: ApiClient, on_success: Callable[[], None] | None = None) -> None:
    page_header(
        "加入训练场",
        "创建账户，开始记录每一次提交与通过。",
        icon="🚀",
        eyebrow="NEW CHALLENGER",
    )
    section_header("账户信息", icon="🪪")
    with st.form("register_form"):
        username = st.text_input(
            "用户名", placeholder=REQUIRED_PLACEHOLDER, help="3–40 个字符"
        )
        password = st.text_input(
            "密码", type="password", placeholder=REQUIRED_PLACEHOLDER, help="至少 6 个字符"
        )
        confirmation = st.text_input(
            "确认密码", type="password", placeholder=REQUIRED_PLACEHOLDER
        )
        submitted = st.form_submit_button("注册", type="primary")
    if not submitted:
        return
    errors = validate_registration(username, password, confirmation)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        api.post("/users/", json={"username": username, "password": password})
    except Exception as exc:
        show_error(exc)
        return

    try:
        api.post("/auth/login", json={"username": username, "password": password})
        user = restore_identity(api)
        prepare_browser_bridge(api)
    except Exception as exc:
        st.success("注册成功。")
        st.warning("自动登录失败，请前往登录页面重试。")
        show_error(exc)
        return

    set_auth_user(user or {})
    st.success("注册成功，已自动登录。")
    if on_success is None:
        st.rerun()
    else:
        on_success()


def render_login(api: ApiClient, on_success: Callable[[], None] | None = None) -> None:
    page_header(
        "欢迎回来",
        "登录后继续你的算法训练和评测挑战。",
        icon="🔐",
        eyebrow="PLAYER SIGN IN",
    )
    section_header("登录信息", icon="👤")
    with st.form("login_form"):
        username = st.text_input("用户名", placeholder=REQUIRED_PLACEHOLDER)
        password = st.text_input(
            "密码", type="password", placeholder=REQUIRED_PLACEHOLDER
        )
        submitted = st.form_submit_button("登录", type="primary")
    if not submitted:
        return
    errors = validate_login(username, password)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        with st.spinner("正在登录..."):
            api.post("/auth/login", json={"username": username, "password": password})
            user = restore_identity(api)
            prepare_browser_bridge(api)
    except ApiError as exc:
        if exc.status_code == 403 and "banned" in exc.message.lower():
            st.error("该用户已被禁用，无法登录。")
        else:
            show_error(exc)
    except Exception as exc:
        show_error(exc)
    else:
        set_auth_user(user or {})
        st.success("登录成功。")
        if on_success is None:
            st.rerun()
        else:
            on_success()


def render_logout(api: ApiClient, on_success: Callable[[], None] | None = None) -> None:
    page_header("退出训练场", "安全结束当前会话，下次登录仍可继续训练。", icon="👋")
    st.warning("退出后，需要重新登录才能继续使用个人功能。")
    if st.button("确认退出", type="primary"):
        try:
            api.post("/auth/logout")
        except ApiError as exc:
            if exc.status_code != 401:
                show_error(exc)
        except Exception as exc:
            show_error(exc)
        finally:
            logout_local(api)
        st.success("已退出登录。")
        if on_success is None:
            st.rerun()
        else:
            on_success()


def render_profile(api: ApiClient, user: dict[str, object]) -> None:
    role = str(user.get("role", "user"))
    if role == "admin":
        page_header(
            "管理员中心",
            "查看管理员账户信息与平台管理概览。",
            icon="🛡️",
            eyebrow="ADMIN ACCOUNT",
        )
    else:
        page_header(
            "个人战绩",
            "查看账户信息与累计训练成果。",
            icon="🏅",
            eyebrow="PLAYER PROFILE",
        )
    try:
        with st.spinner("正在加载个人信息..."):
            data = cached_for_session(
                f"profile:{user['id']}",
                lambda: api.get(f"/users/{user['id']}")["data"],
            )
    except Exception as exc:
        show_error(exc)
        return
    role = str(data.get("role", "user"))
    if role == "admin":
        badges([("管理员", "orange"), ("平台管理权限", "cyan")])
    else:
        badges([("普通用户", "cyan")])
    identity, joined = st.columns(2)
    with identity:
        info_card("用户名", data.get("username", "—"), icon="👤")
    with joined:
        info_card("加入时间", data.get("join_time", "—"), icon="📅")
    section_header("训练统计", icon="📊")
    submitted, resolved = st.columns(2)
    submitted.metric("累计提交", data.get("submit_count", 0))
    resolved.metric("通过题目", data.get("resolve_count", 0))


def render_user_admin(api: ApiClient) -> None:
    page_header(
        "选手管理",
        "查看用户战绩并安全调整角色与账号状态。",
        icon="🛡️",
        eyebrow="ADMIN CONTROL",
    )
    section_header("选手列表", icon="👥")
    page, page_size = pagination_values("user_admin")
    try:
        with st.spinner("正在加载用户..."):
            result = cached_for_session(
                f"users:{page}:{page_size}",
                lambda: api.get(
                    "/users/", params={"page": page, "page_size": page_size}
                )["data"],
            )
    except Exception as exc:
        show_error(exc)
        return
    users = result.get("users", [])
    total = int(result.get("total", 0))
    list_count(total)
    if not users:
        st.info("当前页没有用户。")
        render_pagination("user_admin", total=total)
        return
    role_display = {
        "user": ("普通用户", "cyan"),
        "admin": ("管理员", "orange"),
        "banned": ("已禁用", "red"),
    }
    labels = ("用户 ID", "用户名", "账号状态", "注册日期", "提交次数", "通过题目")
    widths = (1, 2, 1.2, 2, 1, 1)
    with data_table(labels, widths, key="users"):
        for item in users:
            with table_row(labels, widths, key=f"user_{item['user_id']}") as row:
                with row[0]:
                    cell_text(item.get("user_id"), tone="muted")
                with row[1]:
                    cell_text(item.get("username"), emphasis=True)
                role_value = str(item.get("role") or "")
                role_label, role_tone = role_display.get(
                    role_value, (role_value or "—", "cyan")
                )
                with row[2]:
                    badges([(role_label, role_tone)])
                with row[3]:
                    cell_text(item.get("join_time"), tone="muted")
                with row[4]:
                    cell_text(item.get("submit_count", 0), emphasis=True, tone="success")
                with row[5]:
                    cell_text(item.get("resolve_count", 0), emphasis=True, tone="success")

    render_pagination("user_admin", total=total)
    with section_card("角色调整", key="user_role", icon="⚠️", tone="warning"):
        target = st.selectbox(
            "选择用户",
            users,
            format_func=lambda item: f"{item['username']}（{item['role']}）",
        )
        role = st.selectbox("新角色", ["user", "admin", "banned"])
        confirmed = st.checkbox("我确认修改该用户角色；封禁后该账号将立即退出登录。")
        if st.button("修改角色", disabled=not confirmed, type="primary"):
            try:
                api.put(f"/users/{target['user_id']}/role", json={"role": role})
            except Exception as exc:
                show_error(exc)
            else:
                clear_session_cache("users:")
                st.success("用户角色修改成功。")
                st.rerun()
