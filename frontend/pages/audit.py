"""Administrator audit-history page."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error
from frontend.components.layout import cell_text, data_table, section_card, table_row
from frontend.components.pagination import (
    pagination_values,
    render_pagination,
)
from frontend.components.ui import badges, empty_state, list_count, page_header, section_header
from frontend.navigation import restore_widget, save_widgets

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


CHANGE_LABELS = {
    "before": "原值", "after": "新值", "role": "角色", "public_cases": "日志公开",
    "model_name": "模型名称", "provider_url": "服务地址",
    "agent_task_id": "命题任务", "revision": "版本", "status": "状态",
}


def audit_changes_summary(changes: object, action: str = "") -> str:
    """Human-readable preview; the original JSON remains available in the row."""
    if not isinstance(changes, dict) or not changes:
        return "—"

    def value_text(value: Any) -> str:
        if value is None:
            return "未设置"
        if isinstance(value, bool):
            return "是" if value else "否"
        if action == "update_user_role" and isinstance(value, str):
            return {"user": "普通用户", "admin": "管理员", "banned": "已禁用"}.get(value, value)
        if isinstance(value, dict):
            return "、".join(
                f"{CHANGE_LABELS.get(str(key), str(key))}：{value_text(item)}"
                for key, item in value.items()
            ) or "空"
        if isinstance(value, list):
            return "、".join(value_text(item) for item in value) or "空"
        return str(value)

    parts = []
    if "before" in changes and "after" in changes:
        parts.append(f"{value_text(changes['before'])} → {value_text(changes['after'])}")
    for key, value in changes.items():
        if key in {"before", "after"} and "before" in changes and "after" in changes:
            continue
        label = CHANGE_LABELS.get(str(key), str(key))
        if isinstance(value, dict) and "before" in value and "after" in value:
            parts.append(f"{label}：{value_text(value['before'])} → {value_text(value['after'])}")
        else:
            parts.append(f"{label}：{value_text(value)}")
    summary = "；".join(parts)
    return summary if len(summary) <= 100 else summary[:99] + "…"


def _audit_time_text(value: object) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d\n%H:%M:%S")
    except ValueError:
        return str(value)


def render_audit(api: ApiClient) -> None:
    page_header(
        "访问审计",
        "查看系统已记录的全部用户访问与敏感操作历史。",
        icon="🧾",
        eyebrow="ADMIN AUDIT",
    )

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
        save_widgets("audit_user_filter", "audit_action_filter", "audit_result_filter",
                     reset_page="audit_history")

    restore_widget("audit_user_filter", "全部用户", options=user_options)
    restore_widget("audit_action_filter", "全部操作", options=action_options)
    restore_widget("audit_result_filter", "全部结果", options=result_options)

    with section_card("筛选条件", key="audit_filters", icon="🔎", tone="toolbar"):
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
    list_count(total)
    if not logs:
        empty_state("没有符合当前筛选条件的审计记录。", icon="🧾")
    else:
        labels = ("时间（北京时间）", "操作者", "动作", "目标", "结果", "状态码")
        widths = (1.5, 1, 1.5, 2, .8, .7)
        with data_table(labels, widths, key="audit"):
            for index, item in enumerate(logs):
                with table_row(labels, widths, key=f"audit_{page}_{index}") as row:
                    with row[0]:
                        cell_text(_audit_time_text(item.get("created_at")),
                                  tone="timestamp", emphasis=True)
                    with row[1]:
                        cell_text(
                            item.get("username") or (
                                f"用户 #{item['user_id']}" if item.get("user_id") else "已删除用户"
                            ),
                            emphasis=True,
                        )
                    with row[2]:
                        cell_text(audit_action_text(item.get("action")), emphasis=True)
                    with row[3]:
                        cell_text(audit_target_text(item), tone="muted")
                    with row[4]:
                        badges([("成功", "green") if item.get("success") else ("失败", "red")])
                    with row[5]:
                        cell_text(item.get("status"), tone="muted")
    render_pagination("audit_history", total=total, page_size=page_size)
