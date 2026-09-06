"""Render real collection pages against the test's API adapter."""

import streamlit as st

from frontend.pages.problem_banks import render_problem_banks
from frontend.pages.problems import render_problem_list

api = st.session_state["test_api"]
if st.session_state.get("test_page") == "catalogue":
    render_problem_list(api, {"id": 2, "role": "user"})
else:
    render_problem_banks(api, {"id": 2, "role": "user"})
