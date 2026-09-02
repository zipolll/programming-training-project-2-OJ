"""Streamlit application entry point."""

import streamlit as st

from frontend.api_client import ApiClient


def render_home() -> None:
    """Render project status and backend connectivity."""
    st.title("Programming Training OJ")
    st.caption("在线评测系统项目骨架")
    try:
        result = ApiClient().get_health()
    except Exception as exc:  # Streamlit must present connectivity failures to the user.
        st.warning(f"后端尚未连接：{exc}")
    else:
        st.success(f"后端状态：{result['data']['status']}")


def render_placeholder(page: str) -> None:
    """Render a non-functional marker for a future course module."""
    st.title(page)
    st.info("该模块将在后续步骤中实现。")


def main() -> None:
    """Run the Streamlit navigation shell."""
    st.set_page_config(page_title="Programming Training OJ", page_icon="⚖️", layout="wide")
    page = st.sidebar.selectbox(
        "功能",
        ["首页", "题目", "提交", "用户", "评测日志", "AI 智能命题"],
    )
    if page == "首页":
        render_home()
    else:
        render_placeholder(page)


if __name__ == "__main__":
    main()
