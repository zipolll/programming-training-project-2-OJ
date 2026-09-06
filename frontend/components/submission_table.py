"""Reusable, accessible submission result table."""

from collections.abc import Callable, Sequence
from typing import Any

from frontend.components.layout import cell_text, data_table, table_row
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
    labels = ("提交编号", "评测结果", "得分", "总分")
    widths = (1.2, 2.1, 1, 1)
    with data_table(labels, widths, key=f"submissions_{key}"):
        for item in submissions:
            submission_id = str(item["submission_id"])
            with table_row(labels, widths, key=f"{key}_{submission_id}") as row:
                with row[0]:
                    if on_select is None:
                        cell_text(submission_id, emphasis=True)
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
                with row[2]:
                    cell_text(
                        item.get("score"),
                        emphasis=True,
                        tone="success" if tone == "green" else "failure",
                    )
                with row[3]:
                    cell_text(item.get("counts"), emphasis=True)
