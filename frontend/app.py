"""Streamlit application entry point and role-aware navigation."""

from collections.abc import Callable

import streamlit as st

from frontend.components.common import show_error
from frontend.components.theme import apply_theme
from frontend.components.ui import badges, feature_grid, page_header, section_header
from frontend.data_access import load_service_status
from frontend.models import NAVIGATION_METADATA, navigation_sections
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
from frontend.session import (
    auth_resolution_pending,
    current_user,
    get_api_client,
    restore_identity,
    sync_browser_auth,
)


def render_home() -> None:
    page_header(
        "Programming Training OJ",
        "从题目阅读、代码提交到智能命题，一站式完成你的算法训练挑战。",
        icon="🏁",
        eyebrow="READY · CODE · ACCEPT",
    )
    badges([("Python / C++", "cyan"), ("异步评测", "orange"), ("AI 智能命题", "green")])
    feature_grid(
        [
            ("📚", "题库训练", "查看题面、样例和约束，快速进入解题状态。"),
            ("⚡", "在线评测", "提交代码并实时获取编译、运行和得分结果。"),
            ("📈", "成长记录", "筛选提交历史，追踪每一次挑战和突破。"),
            ("✨", "智能命题", "通过受控 AI 工作流生成、验证并导入新题目。"),
        ]
    )
    section_header("服务状态", icon="🛰️")
    api = get_api_client()
    try:
        status = load_service_status(api.base_url, api)
    except Exception as exc:
        show_error(exc)
    else:
        st.success("系统运行正常。" if status == "ok" else f"系统状态：{status}")


def _page(
    renderer: Callable[[], None],
    title: str,
    *,
    default: bool = False,
) -> st.Page:
    metadata = NAVIGATION_METADATA[title]
    return st.Page(
        renderer,
        title=title,
        icon=metadata["icon"],
        url_path=metadata["url_path"],
        default=default,
    )


def render_auth_loading() -> None:
    """Keep the requested route mounted while browser authentication resolves."""
    page_header(
        "正在载入",
        "马上回到你的页面。",
        icon="⏳",
        eyebrow="LOADING",
    )


def run_auth_loading_navigation() -> None:
    """Register every route invisibly so a hard refresh does not fall home."""
    loading_pages = [
        _page(render_auth_loading, title, default=title == "首页")
        for title in NAVIGATION_METADATA
    ]
    st.navigation(loading_pages, position="hidden").run()


def main() -> None:
    st.set_page_config(page_title="Programming Training OJ", page_icon="⚖️", layout="wide")
    apply_theme()
    api = get_api_client()
    try:
        sync_browser_auth(api)
        if current_user() is None and api.has_cookies:
            restore_identity(api)
    except Exception as exc:
        show_error(exc)
    if auth_resolution_pending(api):
        run_auth_loading_navigation()
        st.stop()
    user = current_user()
    role = str(user.get("role")) if user else None

    home_page = _page(render_home, "首页", default=True)
    renderers = {
        "首页": home_page,
    }

    def return_home() -> None:
        st.switch_page(home_page)

    if user is None:
        renderers.update(
            {
                "注册": _page(lambda: render_register(api, return_home), "注册"),
                "登录": _page(lambda: render_login(api, return_home), "登录"),
            }
        )
    else:
        renderers.update(
            {
                "题目列表": _page(lambda: render_problem_list(api, user), "题目列表"),
                "题目管理": _page(
                    lambda: render_problem_management(api, role == "admin"), "题目管理"
                ),
                "AI 智能命题": _page(lambda: render_agent(api), "AI 智能命题"),
                "提交代码": _page(lambda: render_submit(api), "提交代码"),
                "提交记录": _page(
                    lambda: render_submission_list(api, user, role == "admin"), "提交记录"
                ),
                "个人信息": _page(lambda: render_profile(api, user), "个人信息"),
                "退出": _page(lambda: render_logout(api, return_home), "退出"),
            }
        )
        if role == "admin":
            renderers.update(
                {
                    "用户管理": _page(lambda: render_user_admin(api), "用户管理"),
                    "日志可见性": _page(lambda: render_visibility(api), "日志可见性"),
                }
            )

    sections = {
        section: [renderers[title] for title in titles]
        for section, titles in navigation_sections(role).items()
    }
    selected_page = st.navigation(sections, position="sidebar", expanded=True)
    if user:
        st.sidebar.caption(f"当前用户：{user['username']}（{role}）")
    else:
        st.sidebar.caption("当前状态：未登录")
    selected_page.run()


if __name__ == "__main__":
    main()
