"""Administrator audit-history page."""

import json
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error
from frontend.components.pagination import (
    pagination_values,
    render_pagination,
    reset_pagination,
)
from frontend.components.ui import badges, empty_state, page_header, section_header

AUDIT_ACTION_LABELS = {
    "view_logs": "查看测试点日志",
    "update_log_visibility": "修改日志可见性",
    "update_user_role": "修改用户角色",
    "rejudge_submission": "重新评测提交",
    "delete_problem": "删除题目",
    "update_agent_config": "修改 AI 配置",
    "import_agent_problem": "导入 AI 题目",
}

AUDIT_TARGET_LABELS = {
    "submission": "提交",
    "problem": "题目",
    "user": "用户",
    "agent_config": "AI 配置",
}


def audit_action_text(action: object) -> str:
    value = str(action or "")
    return AUDIT_ACTION_LABELS.get(value, value or "未知操作")


def audit_target_text(entry: dict[str, Any]) -> str:
    target_type = str(entry.get("target_type") or "")
    target_id = str(entry.get("target_id") or "—")
    label = AUDIT_TARGET_LABELS.get(target_type, target_type or "对象")
    problem_id = entry.get("problem_id")
    suffix = f" · 题目 {problem_id}" if problem_id else ""
    return f"{label} {target_id}{suffix}"


def audit_changes_text(changes: object) -> str:
    if not isinstance(changes, dict) or not changes:
        return "—"
    return json.dumps(changes, ensure_ascii=False, separators=(", ", ": "))


def _audit_time_text(value: object) -> str:
    return str(value or "—").replace("T", " ", 1)


def render_audit(api: ApiClient) -> None:
    page_header(
        "访问审计",
        "查看系统已记录的全部用户访问与敏感操作历史。",
        icon="🧾",
        eyebrow="ADMIN AUDIT",
    )
    section_header("筛选条件", icon="🔎")

    try:
        user_result = api.get("/users/", params={"page": 1, "page_size": 1000})["data"]
    except Exception as exc:
        show_error(exc)
        return

    users = list(user_result.get("users", []))
    user_options = {"全部用户": None}
    user_options.update(
        {
            f"{item['username']}（#{item['user_id']}）": int(item["user_id"])
            for item in users
        }
    )
    action_options = {"全部操作": None}
    action_options.update({label: action for action, label in AUDIT_ACTION_LABELS.items()})
    result_options: dict[str, bool | None] = {
        "全部结果": None,
        "成功": True,
        "失败": False,
    }

    def filters_changed() -> None:
        reset_pagination("audit_history")

    filters = st.columns(3)
    selected_user = filters[0].selectbox(
        "用户",
        list(user_options),
        key="audit_user_filter",
        on_change=filters_changed,
    )
    selected_action = filters[1].selectbox(
        "操作",
        list(action_options),
        key="audit_action_filter",
        on_change=filters_changed,
    )
    selected_result = filters[2].selectbox(
        "结果",
        list(result_options),
        key="audit_result_filter",
        on_change=filters_changed,
    )

    page, page_size = pagination_values("audit_history", default_page_size=20)
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if user_options[selected_user] is not None:
        params["user_id"] = user_options[selected_user]
    if action_options[selected_action] is not None:
        params["action"] = action_options[selected_action]
    if result_options[selected_result] is not None:
        params["success"] = result_options[selected_result]

    try:
        data = api.get("/logs/audit/", params=params)["data"]
    except Exception as exc:
        show_error(exc)
        return

    total = int(data.get("total", 0))
    logs = list(data.get("logs", []))
    section_header("审计记录", icon="🛡️")
    badges([(f"共 {total} 条", "cyan"), (f"第 {page} 页", "orange")])
    if not logs:
        empty_state("没有符合当前筛选条件的审计记录。", icon="🧾")
    else:
        rows = [
            {
                "时间": _audit_time_text(item.get("created_at")),
                "操作者": item.get("username")
                or (f"用户 #{item['user_id']}" if item.get("user_id") else "已删除用户"),
                "动作": audit_action_text(item.get("action")),
                "目标": audit_target_text(item),
                "结果": "成功" if item.get("success") else "失败",
                "状态码": item.get("status"),
                "变更摘要": audit_changes_text(item.get("changes")),
            }
            for item in logs
        ]
        st.dataframe(rows, hide_index=True, width="stretch")
    render_pagination("audit_history", total=total)
