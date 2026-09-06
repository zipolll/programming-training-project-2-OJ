"""Offline UI fixture: real page renderers, deterministic data, no backend writes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from frontend.components.theme import apply_theme
from frontend.navigation import restore_widget, save_widgets
from frontend.pages import agent, audit, auth, languages, problem_banks, problems, submissions

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview_data import PROBLEM, PreviewApi

st.set_page_config(layout="wide")
st.navigation([st.Page(lambda: None, title="预览", default=True)]).run()
apply_theme()
api = PreviewApi()
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
    "语言注册",
    "代码提交",
    "题目内提交",
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
    agent._authoring_form(api)
elif page == "语言注册":
    languages.render_language_registration(api)
elif page == "代码提交":
    submissions.render_submit(api)
else:
    problems._render_problem_submission_tools(api, PROBLEM, user)
