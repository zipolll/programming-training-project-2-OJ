"""Streamlit AI problem-authoring workflow."""

from decimal import Decimal, InvalidOperation
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import OPTIONAL_PLACEHOLDER, REQUIRED_PLACEHOLDER, show_error
from frontend.components.layout import form_row, section_card
from frontend.components.ui import (
    badges,
    info_card,
    page_header,
    section_header,
)
from frontend.navigation import update_route

TERMINAL = {"success", "error", "cancelled"}
COMMON_CURRENCIES = ["CNY", "USD", "EUR", "GBP", "JPY", "HKD"]
VIEW_LOADING_TEXT = {
    "模型配置": "正在加载模型配置...",
    "新建出题": "正在加载命题选项...",
    "出题记录": "正在加载出题记录...",
    "任务详情": "正在加载任务进度...",
}


def format_cost(value: Any) -> str:
    """Format model usage cost consistently without exposing raw precision."""
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "0.00"


def task_overview_fields(
    task: dict[str, Any],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Build primary, short optional, and long optional task fields."""
    request = task.get("request") or {}
    primary = [
        ("题目类型", str(request.get("problem_type") or "未填写"), "🧩"),
        ("目标难度", str(request.get("difficulty") or "未填写"), "🎯"),
        ("任务版本", f"Revision {task.get('revision', 1)}", "🔁"),
    ]
    short_optional = []
    for label, key, icon in (
        ("期望算法或复杂度", "expected_algorithm", "⚙️"),
        ("数据规模", "data_scale", "📐"),
    ):
        value = str(request.get(key) or "").strip()
        if value:
            short_optional.append((label, value, icon))
    existing_problem = str(request.get("existing_problem_id") or "").strip()
    if request.get("adapt_existing") and existing_problem:
        short_optional.append(("改编自题目", existing_problem, "📝"))

    long_optional = []
    forbidden = "、".join(request.get("forbidden_knowledge") or [])
    if forbidden:
        long_optional.append(("避免使用的知识点", forbidden, "🚫"))
    for label, key, icon in (
        ("背景偏好", "background_preference", "🎨"),
        ("补充要求", "additional_requirements", "💬"),
    ):
        value = str(request.get(key) or "").strip()
        if value:
            long_optional.append((label, value, icon))
    return primary, short_optional, long_optional


def _task_overview(task: dict[str, Any]) -> None:
    """Show enough authoring context to distinguish similar task revisions."""
    request = task.get("request") or {}
    knowledge = "、".join(request.get("required_knowledge") or []) or "未填写"
    primary, short_optional, long_optional = task_overview_fields(task)
    overview = st.columns(len(primary))
    for column, (label, value, icon) in zip(overview, primary, strict=True):
        with column:
            info_card(label, value, icon=icon, compact=True)
    info_card("核心知识点", knowledge, icon="🧠")

    if short_optional or long_optional:
        section_header("更多命题要求", icon="🧰")
    if short_optional:
        optional_columns = st.columns(len(short_optional))
        for column, (label, value, icon) in zip(optional_columns, short_optional, strict=True):
            with column:
                info_card(label, value, icon=icon, compact=True)
    if long_optional:
        with st.container(key="oj_agent_long_requirements"):
            for label, value, icon in long_optional:
                info_card(label, value, icon=icon)

    created_at = str(task.get("created_at") or "").replace("T", " ")[:19]
    details = f"任务编号：{task.get('task_id', '未知')}"
    if created_at:
        details += f" · 创建时间：{created_at}"
    st.caption(details)


def _config(api: ApiClient) -> None:
    try:
        current = api.get("/agent/config")["data"]
    except Exception as exc:
        show_error(exc)
        return
    if not current.get("encryption_configured"):
        st.warning("AI 密钥安全存储尚未配置，目前无法保存 API Key。")
    if current.get("has_api_key"):
        st.caption(f"已保存密钥：{current.get('masked_api_key', '********')}（明文永不返回）")
    config_badges = [
        (
            "凭据加密已启用" if current.get("encryption_configured") else "凭据加密未配置",
            "green" if current.get("encryption_configured") else "red",
        ),
        ("API Key 已保存" if current.get("has_api_key") else "等待 API Key", "cyan"),
    ]
    badges(config_badges)
    with st.form("agent-config"):
        with section_card("模型连接", key="agent_connection", icon="🔌"):
            with form_row("agent_connection", (2, 1)) as fields:
                provider_url = fields[0].text_input(
                    "Provider URL",
                    current.get("provider_url", ""),
                    placeholder=REQUIRED_PLACEHOLDER,
                )
                model_name = fields[1].text_input(
                    "模型名称", current.get("model_name", ""), placeholder=REQUIRED_PLACEHOLDER
                )
            api_key = st.text_input(
                "API Key（留空则保留）", type="password", placeholder=OPTIONAL_PLACEHOLDER
            )
        with section_card("Token 价格", key="agent_prices", icon="💳"):
            left, right, currency_column = st.columns(3)
            input_price = left.number_input(
                "输入价格 / 百万 Token",
                min_value=0.0,
                value=float(current.get("input_price_per_million_tokens", 0)),
            )
            output_price = right.number_input(
                "输出价格 / 百万 Token",
                min_value=0.0,
                value=float(current.get("output_price_per_million_tokens", 0)),
            )
            current_currency = str(current.get("currency", "USD"))
            currency_options = list(COMMON_CURRENCIES)
            if current_currency not in currency_options:
                currency_options.append(current_currency)
            currency = currency_column.selectbox(
                "币种",
                currency_options,
                index=currency_options.index(current_currency),
                accept_new_options=True,
                help="可从列表选择，也可以直接输入其他币种代码。",
            )
        with section_card("执行策略", key="agent_policy", icon="⚙️"):
            st.caption(
                "每次任务最多 4 分钟，包含排队、生成、修正和验证；到时停止并保留已有内容。"
                "GLM-5.3 使用低思考强度，实际单次输出上限为 16000 Token。"
            )
            policy_fields = st.columns(3)
            timeout = policy_fields[0].number_input(
                "请求超时（秒）",
                1.0,
                240.0,
                min(240.0, float(current.get("request_timeout", 180.0))),
            )
            iterations = policy_fields[1].number_input(
                "最大修正轮数", 1, 10, int(current.get("max_iterations", 3))
            )
            max_tokens = policy_fields[2].number_input(
                "单次最大输出 Token",
                256,
                128000,
                int(current.get("max_output_tokens", 50000)),
            )
        with st.container(horizontal=True):
            saved = st.form_submit_button("保存配置")
            test_connection = st.form_submit_button("测试模型连接")
    if saved:
        config_errors = []
        if not provider_url.strip():
            config_errors.append("请输入服务地址。")
        if not model_name.strip():
            config_errors.append("请输入模型名称。")
        if not currency or not currency.strip():
            config_errors.append("请输入币种。")
        if not current.get("has_api_key") and not api_key:
            config_errors.append("请输入 API Key。")
        if config_errors:
            for message in config_errors:
                st.error(message)
            return
        payload = {
            "provider_url": provider_url,
            "model_name": model_name,
            "input_price_per_million_tokens": str(input_price),
            "output_price_per_million_tokens": str(output_price),
            "currency": currency.strip(),
            "request_timeout": timeout,
            "max_iterations": iterations,
            "max_output_tokens": max_tokens,
        }
        if api_key:
            payload["api_key"] = api_key
        try:
            api.put("/agent/config", json=payload)
        except Exception as exc:
            show_error(exc)
        else:
            st.success("配置已加密保存。")
    if test_connection:
        try:
            api.post("/agent/config/test")
        except Exception as exc:
            show_error(exc)
        else:
            st.success("模型连接正常。")


def _select_agent_view() -> None:
    update_route(agent_active_view=st.session_state.agent_nav_selection)


def render_agent(api: ApiClient, *, embedded: bool = False) -> None:
    from frontend.pages.agent_workspace import (
        authoring_form,
        record_list,
        task_monitor,
    )

    if not embedded:
        page_header("AI 智能命题", "描述需求，生成题目，在同一记录中持续完善。")
    views = ["新建出题", "出题记录"]
    aliases = {"创建任务": "新建出题", "进度与结果": "任务详情"}
    requested = st.query_params.get("agent_active_view", "新建出题")
    view = aliases.get(requested, requested)
    if view not in [*views, "任务详情", "模型配置"]:
        view = "新建出题"
    with st.container(key="oj_agent_navigation"):
        nav, settings = st.columns([5, 1], vertical_alignment="center")
    st.session_state.agent_nav_selection = view if view in views else None
    nav.segmented_control(
        "AI 出题功能",
        views,
        key="agent_nav_selection",
        label_visibility="collapsed",
        on_change=_select_agent_view,
    )
    if settings.button("模型配置", key="agent_settings_link"):
        update_route(agent_active_view="模型配置")
        st.rerun()
    with st.container(key="agent_view_content"), st.spinner(VIEW_LOADING_TEXT[view]):
        if view == "模型配置":
            _config(api)
        elif view == "新建出题":
            authoring_form(api)
        elif view == "出题记录":
            record_list(api)
        else:
            task_monitor(api)
