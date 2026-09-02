"""Streamlit application entry point and role-aware navigation."""

import streamlit as st

from frontend.components.common import show_error
from frontend.models import navigation_for
from frontend.pages.agent import render_agent
from frontend.pages.auth import (
    render_login,
    render_logout,
    render_profile,
    render_register,
    render_user_admin,
)
from frontend.pages.problems import render_problem_list, render_problem_management
from frontend.pages.submissions import (
    render_submission_list,
    render_submit,
    render_visibility,
)
from frontend.session import current_user, get_api_client, restore_identity


def render_home() -> None:
    st.title("Programming Training OJ")
    st.caption("课程 Step 6 · Streamlit 前端交互")
    api = get_api_client()
    try:
        result = api.get_health()
    except Exception as exc:
        show_error(exc)
    else:
        st.success(f"后端状态：{result['data']['status']}")
    st.markdown("通过左侧导航访问用户、题目、提交和评测日志功能。")


def main() -> None:
    st.set_page_config(page_title="Programming Training OJ", page_icon="⚖️", layout="wide")
    api = get_api_client()
    try:
        restore_identity(api)
    except Exception as exc:
        show_error(exc)
    user = current_user()
    role = str(user.get("role")) if user else None
    if user:
        st.sidebar.caption(f"当前用户：{user['username']}（{role}）")
    else:
        st.sidebar.caption("当前状态：未登录")
    page = st.sidebar.selectbox("功能", navigation_for(role))
    if page == "首页":
        render_home()
    elif page == "注册":
        render_register(api)
    elif page == "登录":
        render_login(api)
    elif page == "退出":
        render_logout(api)
    elif page == "题目列表":
        render_problem_list(api)
    elif page == "AI 智能命题" and role == "admin":
        render_agent(api)
    elif user is None:
        st.error("请先登录。")
    elif page == "个人信息":
        render_profile(api, user)
    elif page == "题目管理":
        render_problem_management(api, role == "admin")
    elif page == "提交代码":
        render_submit(api)
    elif page == "提交记录":
        render_submission_list(api, user, role == "admin")
    elif page == "用户管理" and role == "admin":
        render_user_admin(api)
    elif page == "日志可见性" and role == "admin":
        render_visibility(api)
    else:
        st.error("权限不足。")


if __name__ == "__main__":
    main()
