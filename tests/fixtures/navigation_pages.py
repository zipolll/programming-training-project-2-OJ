"""Real multipage navigation using the production page renderers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from preview_data import PreviewApi

from frontend.components.theme import apply_theme
from frontend.navigation import mount_navigation
from frontend.pages import problem_banks, problems, submissions

st.set_page_config(layout="wide")
apply_theme()
api = PreviewApi()
user = {"id": 1, "role": "admin"}
st.session_state["auth_user"] = user
catalogue = st.Page(lambda: problems.render_problem_list(api, user),
                    title="题目列表", default=True)
history = st.Page(lambda: submissions.render_submission_list(api, user, True),
                  title="提交记录", url_path="submissions")
banks = st.Page(lambda: problem_banks.render_problem_banks(api, user),
                title="我的题库", url_path="problem-banks")
management = st.Page(lambda: problems.render_problem_management(api),
                     title="命题中心", url_path="problem-management")
nav = st.navigation([catalogue, history, banks, management])
st.session_state["oj_submission_page"] = history
st.session_state["oj_bank_page"] = banks
st.session_state["oj_problems_page"] = catalogue
mount_navigation()
nav.run()
