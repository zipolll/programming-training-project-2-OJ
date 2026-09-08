"""Exercise the production authoring UI against a real test API."""

import streamlit as st

from frontend.components.theme import apply_theme
from frontend.pages.agent import render_agent

st.set_page_config(layout="wide")
apply_theme()
render_agent(st.session_state["test_api"], embedded=True)
