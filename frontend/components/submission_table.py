"""Reusable, accessible submission result table."""

from collections.abc import Callable, Sequence
from typing import Any

import streamlit as st

from frontend.components.ui import badges


def submission_outcome(item: dict[str, Any]) -> tuple[str, str]:
    """Return a textual result and color tone from course-compatible summary data."""
    status = str(item.get("status") or "")
    if status == "pending":
        return "等待评测", "cyan oj-badge--pending"
    if status == "error":
        return "评测异常", "orange"
    score = item.get("score")
    counts = item.get("counts")
    if status == "success" and score is not None and counts is not None:
        if int(score) >= int(counts):
            return "答案正确（AC）", "green"
        return "未完全通过", "red"
    if status == "success":
        return "评测完成", "green"
    return "状态未知", "orange"


def render_submission_table(
    submissions: Sequence[dict[str, Any]],
    *,
    key: str,
    on_select: Callable[[str], None] | None = None,
) -> None:
    """Render a compact result table; IDs become links when a callback is supplied."""
    with st.container(key=f"submission_catalog_{key}"):
        header = st.columns([1.2, 2.1, 1, 1])
        header[0].markdown("**提交编号**")
        header[1].markdown("**评测结果**")
        header[2].markdown("**得分**")
        header[3].markdown("**总分**")
        for item in submissions:
            submission_id = str(item["submission_id"])
            row = st.columns([1.2, 2.1, 1, 1])
            if on_select is None:
                row[0].write(submission_id)
            else:
                row[0].button(
                    submission_id,
                    key=f"{key}_submission_{submission_id}",
                    on_click=on_select,
                    args=(submission_id,),
                    help=f"查看提交 {submission_id} 的详情",
                )
            label, tone = submission_outcome(item)
            with row[1]:
                badges([(label, tone)])
            score = item.get("score") if item.get("score") is not None else "—"
            counts = item.get("counts") if item.get("counts") is not None else "—"
            row[2].markdown(f"<div class='oj-result-number'>{score}</div>", unsafe_allow_html=True)
            row[3].markdown(f"<div class='oj-result-number'>{counts}</div>", unsafe_allow_html=True)
