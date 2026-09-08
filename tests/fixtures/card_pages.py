"""Offline UI fixture: real page renderers, deterministic data, no backend writes."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from frontend import app as frontend_app
from frontend.components.theme import apply_theme
from frontend.navigation import restore_widget, save_widgets
from frontend.pages import agent, audit, auth, languages, problem_banks, problems, submissions

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview_data import PROBLEM, AgentPreviewApi, PreviewApi

st.set_page_config(layout="wide")
st.navigation([st.Page(lambda: None, title="预览", default=True)]).run()
apply_theme()
api = PreviewApi()
st.session_state["fixture_rich"] = st.query_params.get("rich") == "1"
if st.session_state["fixture_rich"]:
    api.base_url += "/rich"
user = {"id": 1, "role": "admin"}
st.session_state["auth_user"] = user
pages = [
    "我的题库",
    "题库",
    "提交记录",
    "测试点",
    "用户管理",
    "访问审计",
    "普通命题",
    "编辑题目",
    "模型配置",
    "AI 命题",
    "AI 记录",
    "AI 结果",
    "AI 异常",
    "AI 进度",
    "语言注册",
    "代码提交",
    "题目内提交",
    "首页",
    "登录",
    "注册",
    "个人信息",
    "管理员信息",
]
if "fixture_page" in st.query_params:
    restore_widget("fixture_page", "我的题库", options=pages)
page = st.selectbox("预览页面", pages, key="fixture_page", on_change=save_widgets,
                    args=("fixture_page",))
if st.query_params.get("submission"):
    submissions.render_submission_list(api, user, True)
    st.stop()
if page == "我的题库":
    problem_banks.render_problem_banks(api, user)
elif page == "题库":
    problems.render_problem_list(api, user)
elif page == "提交记录":
    submissions.render_submission_list(api, user, True)
elif page == "测试点":
    submissions._render_log(api, "2")
elif page == "用户管理":
    auth.render_user_admin(api)
elif page == "访问审计":
    audit.render_audit(api)
elif page in {"普通命题", "编辑题目"}:
    payload = problems._problem_form(PROBLEM if page == "编辑题目" else None, "fixture")
    if payload is not None:
        st.session_state["fixture_payload"] = payload
elif page == "模型配置":
    agent._config(api)
elif page == "AI 命题":
    from frontend.pages.agent_workspace import authoring_form
    authoring_form(AgentPreviewApi())
elif page == "AI 记录":
    from frontend.pages.agent_workspace import record_list
    record_list(AgentPreviewApi())
elif page in {"AI 结果", "AI 异常", "AI 进度"}:
    scenario = {"AI 结果": "success", "AI 异常": "error", "AI 进度": "running"}[page]
    from frontend.pages.agent_workspace import task_monitor
    st.session_state.setdefault("agent_task_id", "fixture-2")
    task_monitor(AgentPreviewApi(scenario))
elif page == "语言注册":
    languages.render_language_registration(api)
elif page == "代码提交":
    submissions.render_submit(api)
elif page == "首页":
    with patch.object(frontend_app, "get_api_client", return_value=api):
        frontend_app.render_home()
elif page == "登录":
    auth.render_login(api)
elif page == "注册":
    auth.render_register(api)
elif page in {"个人信息", "管理员信息"}:
    user["role"] = "user" if page == "个人信息" else "admin"
    auth.render_profile(api, user)
else:
    problems._render_problem_submission_tools(api, PROBLEM, user)
