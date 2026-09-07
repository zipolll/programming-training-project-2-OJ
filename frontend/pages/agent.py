"""Streamlit AI problem-authoring workflow."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import OPTIONAL_PLACEHOLDER, REQUIRED_PLACEHOLDER, show_error
from frontend.components.layout import form_row, section_card
from frontend.components.ui import (
    badges,
    empty_state,
    info_card,
    list_count,
    page_header,
    section_header,
    status_badge,
    timeline_event,
)
from frontend.data_access import invalidate_problem_cache, load_problem_summaries
from frontend.models import (
    DIFFICULTY_LEVELS,
    OTHER_OPTION,
    PROBLEM_TYPES,
    resolve_catalogue_option,
)
from frontend.navigation import restore_widget, save_widgets, update_route

TERMINAL = {"success", "error", "cancelled"}
COMMON_CURRENCIES = ["CNY", "USD", "EUR", "GBP", "JPY", "HKD"]
VIEW_LOADING_TEXT = {
    "模型配置": "正在加载模型配置...",
    "创建任务": "正在加载命题选项...",
    "进度与结果": "正在加载任务进度...",
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
        for column, (label, value, icon) in zip(
            optional_columns, short_optional, strict=True
        ):
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
                    "Provider URL", current.get("provider_url", ""),
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
            policy_fields = st.columns(3)
            timeout = policy_fields[0].number_input(
                "请求超时（秒）", 1.0, 600.0, float(current.get("request_timeout", 360.0))
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


def _authoring_form(api: ApiClient) -> None:
    section_header("命题任务", icon="✨")
    try:
        problems = load_problem_summaries(api.base_url, api)
    except Exception:
        problems = []
    with st.form("agent-authoring"):
        with section_card("命题方向", key="agent_direction", icon="🎯"):
            knowledge = st.text_input(
                "核心知识点",
                placeholder=REQUIRED_PLACEHOLDER,
                help="多个知识点使用逗号分隔；生成的解法必须使用这些知识点。",
            )
            difficulty_col, type_col = st.columns(2)
            difficulty_choice = difficulty_col.selectbox(
                "目标难度",
                [*DIFFICULTY_LEVELS, OTHER_OPTION],
            )
            difficulty_other = ""
            if difficulty_choice == OTHER_OPTION:
                difficulty_other = difficulty_col.text_input(
                    "其它难度",
                    placeholder="请输入自定义难度",
                )
            problem_type_choice = type_col.selectbox(
                "题目类型",
                [*PROBLEM_TYPES, OTHER_OPTION],
                index=1,
                help="选择“其它”后可填写自定义题型。",
            )
            problem_type_other = ""
            if problem_type_choice == OTHER_OPTION:
                problem_type_other = type_col.text_input(
                    "其它题型",
                    placeholder="请输入自定义题型",
                )
            difficulty = resolve_catalogue_option(difficulty_choice, difficulty_other)
            problem_type = resolve_catalogue_option(
                problem_type_choice, problem_type_other
            )
            additional = st.text_area(
                "补充要求", placeholder=OPTIONAL_PLACEHOLDER, height=100
            )

        with st.expander("高级设置（选填）"):
            with section_card("生成限制", key="agent_generation", icon="🧠"):
                algorithm = st.text_input(
                    "期望算法或复杂度",
                    placeholder=OPTIONAL_PLACEHOLDER,
                    help="例如：双指针、O(n log n)。留空时由 AI 选择。",
                )
                forbidden = st.text_input(
                    "避免使用的知识点",
                    placeholder=OPTIONAL_PLACEHOLDER,
                    help="多个知识点使用逗号分隔；生成的解法不会采用这些内容。",
                )
                scale = st.text_input(
                    "数据规模",
                    placeholder=OPTIONAL_PLACEHOLDER,
                    help="例如：n ≤ 100000。留空时由 AI 结合资源限制确定。",
                )
            with section_card("评测设置", key="agent_limits", icon="⏱️"):
                left, right = st.columns(2)
                time_limit = left.number_input("时间限制（秒）", 0.1, 60.0, 2.0)
                memory_limit = right.number_input("内存限制（MB）", 16, 4096, 128)
                testcase_count = st.number_input("测试点数量", 1, 100, 10)
            with section_card("背景与改编", key="agent_background", icon="🎨"):
                background = st.text_input("背景偏好", placeholder=OPTIONAL_PLACEHOLDER)
                adapt = st.checkbox("基于已有题目改编")
                options = [""] + [item["id"] for item in problems]
                existing = st.selectbox("已有题目", options, disabled=not adapt)
        submitted = st.form_submit_button("创建命题任务")
    if submitted:
        form_errors = []
        if not knowledge.strip():
            form_errors.append("请输入核心知识点。")
        if not difficulty:
            form_errors.append("请输入其它难度。")
        if not problem_type.strip():
            form_errors.append("请输入其它题型。")
        if adapt and not existing:
            form_errors.append("请选择需要改编的已有题目。")
        if form_errors:
            for message in form_errors:
                st.error(message)
            return
        payload = {
            "required_knowledge": [x.strip() for x in knowledge.split(",") if x.strip()],
            "difficulty": difficulty,
            "problem_type": problem_type,
            "expected_algorithm": algorithm,
            "forbidden_knowledge": [x.strip() for x in forbidden.split(",") if x.strip()],
            "data_scale": scale,
            "time_limit": time_limit,
            "memory_limit": memory_limit,
            "background_preference": background,
            "testcase_count": testcase_count,
            "additional_requirements": additional,
            "adapt_existing": adapt,
            "existing_problem_id": existing or None,
        }
        try:
            result = api.post("/agent/tasks", json=payload)["data"]
        except Exception as exc:
            show_error(exc)
        else:
            update_route(agent_task_id=result["task_id"], agent_active_view="进度与结果")
            st.session_state.agent_events = []
            st.session_state.agent_after_id = 0
            st.success("任务已进入队列。")
            st.rerun()


def _result(api: ApiClient, task: dict[str, Any]) -> None:
    with section_card("资源消耗", key="agent_usage", icon="📊"):
        usage = st.columns(4)
        usage[0].metric("输入 Token", task["input_tokens"])
        usage[1].metric("输出 Token", task["output_tokens"])
        usage[2].metric("总 Token", task["total_tokens"])
        usage[3].metric("费用", f"{format_cost(task['cost'])} {task['currency']}")
        if task["usage_estimated"]:
            st.caption("费用与 Token 数量为估算值。")
    generated = task.get("final_problem") or task.get("draft")
    if generated:
        problem = generated["problem"]
        with st.container(border=False, key=f"agent_problem_detail_{task['task_id']}"):
            section_header("题目详情", icon="📘")
            badges(
                [
                    (str(problem.get("difficulty", "未标注难度")), "orange"),
                    (f"{len(problem.get('testcases', []))} 个测试点", "cyan"),
                    *((str(tag), "green") for tag in problem.get("tags", [])),
                ]
            )
            st.markdown(f"## {problem['title']}")
            section_header("题目描述", icon="📖")
            st.markdown(problem["description"])
            section_header("输入说明", icon="📥")
            st.markdown(problem["input_description"])
            section_header("输出说明", icon="📤")
            st.markdown(problem["output_description"])
            section_header("约束", icon="📐")
            st.markdown(problem["constraints"])
            section_header("样例", icon="🧪")
            for index, sample in enumerate(problem.get("samples", []), 1):
                st.markdown(f"#### 样例 {index}")
                left, right = st.columns(2)
                left.code(sample["input"], language=None)
                right.code(sample["output"], language=None)
            with st.expander("查看测试点", expanded=False):
                for index, testcase in enumerate(problem.get("testcases", []), 1):
                    st.markdown(f"**测试点 {index}**")
                    left, right = st.columns(2)
                    left.code(testcase["input"], language=None)
                    right.code(testcase["output"], language=None)
        with st.expander("参考解法与程序"):
            st.write(generated["solution_explanation"])
            st.write(generated["complexity_analysis"])
            st.code(
                generated["reference_solution"],
                language=generated["reference_solution_language"],
            )
    if task.get("validation_report"):
        with st.expander("验证报告", expanded=False):
            st.json(task["validation_report"])
    if task["status"] == "success":
        with section_card("修订与导入", key="agent_review"):
            feedback = st.text_area(
                "继续修改",
                key=f"feedback-{task['task_id']}",
                placeholder=REQUIRED_PLACEHOLDER,
            )
            if st.button("创建新 revision") and feedback:
                try:
                    result = api.post(
                        f"/agent/tasks/{task['task_id']}/refine", json={"feedback": feedback}
                    )["data"]
                    update_route(agent_task_id=result["task_id"])
                    st.session_state.agent_events = []
                    st.session_state.agent_after_id = 0
                    st.rerun()
                except Exception as exc:
                    show_error(exc)
            confirmed = st.checkbox("我已人工审阅并确认导入", key=f"confirm-{task['task_id']}")
            if st.button("导入题库", disabled=not confirmed):
                try:
                    result = api.post(
                        f"/agent/tasks/{task['task_id']}/import",
                        json={"confirm": True, "update_existing": False},
                    )["data"]
                except Exception as exc:
                    show_error(exc)
                else:
                    invalidate_problem_cache()
                    st.success(f"已导入题目 {result['problem_id']}。")


def _task_monitor(api: ApiClient) -> None:
    with section_card("任务进度与版本", key="agent_history", icon="🧭"):
        try:
            tasks = api.get("/agent/tasks")["data"]
        except Exception as exc:
            show_error(exc)
            return
        list_count(len(tasks))
        if not tasks:
            empty_state("尚无命题任务，请先在“创建任务”中发起挑战。", icon="🤖")
            return
        labels = {
            item["task_id"]: (
                f"revision {item['revision']} · {item['status']} · {item['task_id'][:8]}"
            )
            for item in tasks
        }
        restore_widget("agent_task_id", tasks[0]["task_id"], options=labels)
        selected = st.selectbox(
            "版本历史", list(labels), format_func=labels.get, key="agent_task_id",
            on_change=save_widgets, args=("agent_task_id",),
        )
        if st.session_state.get("agent_events_task") != selected:
            st.session_state.agent_events_task = selected
            st.session_state.agent_events = []
            st.session_state.agent_after_id = 0
        selected_status = next(item["status"] for item in tasks if item["task_id"] == selected)
        pause_key = f"agent-poll-paused-{selected}"
        if st.session_state.get(pause_key):
            st.warning("网络错误后已暂停自动轮询。")
            if st.button("重试轮询"):
                st.session_state[pause_key] = False
                st.rerun()
    interval = (
        1
        if selected_status in {"pending", "running"} and not st.session_state.get(pause_key, False)
        else None
    )

    @st.fragment(run_every=interval)
    def poll() -> None:
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-monitor") as pool:
                task_future = pool.submit(api.get, f"/agent/tasks/{selected}")
                events_future = pool.submit(
                    api.get,
                    f"/agent/tasks/{selected}/events",
                    params={"after_id": st.session_state.get("agent_after_id", 0)},
                )
                task = task_future.result()["data"]
                events = events_future.result()["data"]
        except Exception as exc:
            st.session_state[pause_key] = True
            st.session_state.agent_poll_error = str(exc)
            st.rerun()
        known = {item["event_id"] for item in st.session_state.get("agent_events", [])}
        merged = st.session_state.get("agent_events", []) + [
            item for item in events if item["event_id"] not in known
        ]
        st.session_state.agent_events = merged
        if merged:
            st.session_state.agent_after_id = merged[-1]["event_id"]
        with section_card("执行进度", key="agent_progress"):
            st.progress(task["progress"] / 100, text=f"{task['stage']} · {task['status']}")
            status_badge(str(task["status"]))
            if task["status"] in {"pending", "running"} and st.button("中断任务"):
                try:
                    api.post(f"/agent/tasks/{selected}/cancel")
                except Exception as exc:
                    show_error(exc)
        with section_card("命题要求", key="agent_request"):
            _task_overview(task)
        with section_card("任务事件", key="agent_events", icon="📜"):
            list_count(len(merged))
            for event in merged[-30:]:
                timeline_event(event["timestamp"], event["stage"], event["message"])
        if task["status"] in TERMINAL:
            _result(api, task)
            if selected_status not in TERMINAL:
                st.rerun()

    poll()


def render_agent(api: ApiClient, *, embedded: bool = False) -> None:
    if embedded:
        section_header("AI 智能命题", icon="🤖")
        st.caption("创建、验证并人工确认一套完整题目。")
    else:
        page_header(
            "AI Agent 智能命题",
            "把命题需求转化为经过多轮生成、执行验证和人工确认的完整题目。",
            icon="🤖",
            eyebrow="AI PROBLEM ARENA",
            variant="ai",
        )
    restore_widget("agent_active_view", "模型配置", options=["模型配置", "创建任务", "进度与结果"])
    selected_view = st.segmented_control(
        "功能",
        ["模型配置", "创建任务", "进度与结果"],
        label_visibility="collapsed",
        key="agent_active_view",
        on_change=save_widgets, args=("agent_active_view",),
    )
    view = selected_view or "模型配置"
    with st.container(key="agent_view_content"), st.spinner(VIEW_LOADING_TEXT[view]):
        if view == "模型配置":
            _config(api)
        elif view == "创建任务":
            _authoring_form(api)
        else:
            _task_monitor(api)
