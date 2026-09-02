"""Registration, login, profile, logout, and user administration pages."""

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error
from frontend.errors import ApiError
from frontend.models import validate_registration
from frontend.session import logout_local, restore_identity, set_auth_user


def render_register(api: ApiClient) -> None:
    st.title("用户注册")
    with st.form("register_form"):
        username = st.text_input("用户名 *", help="3–40 个字符")
        password = st.text_input("密码 *", type="password", help="至少 6 个字符")
        confirmation = st.text_input("确认密码 *", type="password")
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
    else:
        st.success("注册成功，请前往登录。")


def render_login(api: ApiClient) -> None:
    st.title("用户登录")
    with st.form("login_form"):
        username = st.text_input("用户名 *")
        password = st.text_input("密码 *", type="password")
        submitted = st.form_submit_button("登录", type="primary")
    if not submitted:
        return
    try:
        api.post("/auth/login", json={"username": username, "password": password})
        user = restore_identity(api)
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
        st.rerun()


def render_logout(api: ApiClient) -> None:
    st.title("退出登录")
    st.warning("退出后将清除当前页面会话中的登录 Cookie。")
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
        st.rerun()


def render_profile(api: ApiClient, user: dict[str, object]) -> None:
    st.title("个人信息")
    try:
        data = api.get(f"/users/{user['id']}")["data"]
    except Exception as exc:
        show_error(exc)
        return
    labels = {
        "username": "用户名",
        "role": "角色",
        "join_time": "注册时间",
        "submit_count": "提交次数",
        "resolve_count": "通过题数",
    }
    for field, label in labels.items():
        st.write(f"**{label}：** {data.get(field, '—')}")


def render_user_admin(api: ApiClient) -> None:
    st.title("用户管理")
    page_size = st.selectbox("每页数量", [10, 20, 50], index=0)
    page = int(st.number_input("页码", min_value=1, value=1))
    try:
        result = api.get("/users/", params={"page": page, "page_size": page_size})["data"]
    except Exception as exc:
        show_error(exc)
        return
    users = result.get("users", [])
    st.caption(f"共 {result.get('total', 0)} 位用户")
    if not users:
        st.info("当前页没有用户。")
        return
    st.dataframe(users, use_container_width=True, hide_index=True)
    target = st.selectbox(
        "选择用户",
        users,
        format_func=lambda item: f"{item['username']}（{item['role']}）",
    )
    role = st.selectbox("新角色", ["user", "admin", "banned"])
    confirmed = st.checkbox("我确认修改该用户角色；封禁会使其现有 Session 失效。")
    if st.button("修改角色", disabled=not confirmed, type="primary"):
        try:
            api.put(f"/users/{target['user_id']}/role", json={"role": role})
        except Exception as exc:
            show_error(exc)
        else:
            st.success("角色已由后端更新。")
            st.rerun()
