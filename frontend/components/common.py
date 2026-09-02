"""Shared display helpers."""

from collections.abc import Callable
from typing import Any

import streamlit as st

from frontend.errors import ApiError, NetworkError
from frontend.models import status_text


def show_error(exc: Exception) -> None:
    if isinstance(exc, (ApiError, NetworkError)):
        st.error(exc.user_message)
    else:
        st.error("操作失败，请稍后重试。")


def render_status(status: str | None) -> None:
    text = status_text(status)
    if status == "pending":
        st.info(text, icon="⏳")
    elif status == "error" or status in {"WA", "CE", "RE", "TLE", "MLE", "UNK"}:
        st.error(text, icon="❌")
    else:
        st.success(text, icon="✅")


def confirmation(key: str, label: str, action: Callable[[], Any]) -> None:
    confirmed = st.checkbox("我已确认该高风险操作", key=f"{key}_confirm")
    if st.button(label, type="primary", disabled=not confirmed, key=f"{key}_button"):
        action()
