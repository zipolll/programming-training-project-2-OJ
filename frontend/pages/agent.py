"""Streamlit AI problem-authoring workflow."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error
from frontend.components.ui import (
    badges,
    empty_state,
    page_header,
    section_header,
    status_badge,
    timeline_event,
)
from frontend.data_access import invalidate_problem_cache, load_problem_summaries

TERMINAL = {"success", "error", "cancelled"}
COMMON_CURRENCIES = ["CNY", "USD", "EUR", "GBP", "JPY", "HKD"]


def _config(api: ApiClient) -> None:
    section_header("模型连接", icon="🔌")
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
        provider_url = st.text_input("Provider URL", current.get("provider_url", ""))
        model_name = st.text_input("模型名称", current.get("model_name", ""))
        api_key = st.text_input("API Key（留空则保留）", type="password")
        section_header("Token 价格", icon="💳")
        left, right = st.columns(2)
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
        currency = st.selectbox(
            "币种",
            currency_options,
            index=currency_options.index(current_currency),
            accept_new_options=True,
            help="可从列表选择，也可以直接输入其他币种代码。",
        )
        section_header("执行策略", icon="⚙️")
        timeout = st.number_input(
            "请求超时（秒）", 1.0, 600.0, float(current.get("request_timeout", 60.0))
        )
        iterations = st.number_input("最大修正轮数", 1, 10, int(current.get("max_iterations", 3)))
        max_tokens = st.number_input(
            "单次最大输出 Token",
            256,
            128000,
            int(current.get("max_output_tokens", 4096)),
        )
        saved = st.form_submit_button("保存配置")
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
    if st.button("测试模型连接"):
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
        section_header("核心目标", icon="🎯")
        knowledge = st.text_input("必须覆盖的知识点（逗号分隔）")
        difficulty = st.selectbox("目标难度", ["入门", "简单", "中等", "困难"])
        problem_type = st.text_input("题目类型", "算法题")
        section_header("算法约束", icon="🧠")
        algorithm = st.text_input("期望算法或复杂度")
        forbidden = st.text_input("禁止知识点（逗号分隔）")
        scale = st.text_input("数据规模")
        section_header("评测资源", icon="⏱️")
        left, right = st.columns(2)
        time_limit = left.number_input("时间限制（秒）", 0.1, 60.0, 2.0)
        memory_limit = right.number_input("内存限制（MB）", 16, 4096, 128)
        testcase_count = st.number_input("测试点数量", 1, 100, 10)
        section_header("背景与改编", icon="🎨")
        background = st.text_input("背景偏好")
        adapt = st.checkbox("基于已有题目改编")
        options = [""] + [item["id"] for item in problems]
        existing = st.selectbox("已有题目", options, disabled=not adapt)
        section_header("补充要求", icon="📝")
        additional = st.text_area("补充要求")
        submitted = st.form_submit_button("创建命题任务")
    if submitted:
        form_errors = []
        if not knowledge.strip():
            form_errors.append("请输入必须覆盖的知识点。")
        if not problem_type.strip():
            form_errors.append("请输入题目类型。")
        if not algorithm.strip():
            form_errors.append("请输入期望算法或复杂度。")
        if not scale.strip():
            form_errors.append("请输入数据规模。")
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
            st.session_state.agent_task_id = result["task_id"]
            st.session_state.agent_events = []
            st.session_state.agent_after_id = 0
            st.success("任务已进入队列。")


def _result(api: ApiClient, task: dict[str, Any]) -> None:
    section_header("资源消耗", icon="📊")
    usage = st.columns(4)
    usage[0].metric("输入 Token", task["input_tokens"])
    usage[1].metric("输出 Token", task["output_tokens"])
    usage[2].metric("总 Token", task["total_tokens"])
    suffix = "（估算）" if task["usage_estimated"] else ""
    usage[3].metric("费用", f"{task['cost']} {task['currency']} {suffix}")
    generated = task.get("final_problem") or task.get("draft")
    if generated:
        problem = generated["problem"]
        section_header(problem["title"], icon="📘")
        badges(
            [
                (str(problem.get("difficulty", "未标注难度")), "orange"),
                (f"{len(problem.get('testcases', []))} 个测试点", "cyan"),
            ]
        )
        st.markdown(problem["description"])
        section_header("输入", icon="📥")
        st.markdown(problem["input_description"])
        section_header("输出", icon="📤")
        st.markdown(problem["output_description"])
        section_header("约束", icon="📐")
        st.markdown(problem["constraints"])
        st.json({"samples": problem["samples"], "testcase_count": len(problem["testcases"])})
        with st.expander("参考解法与程序"):
            st.write(generated["solution_explanation"])
            st.write(generated["complexity_analysis"])
            st.code(
                generated["reference_solution"],
                language=generated["reference_solution_language"],
            )
    if task.get("validation_report"):
        with st.expander("验证报告", expanded=True):
            st.json(task["validation_report"])
    if task["status"] == "success":
        feedback = st.text_area("继续修改", key=f"feedback-{task['task_id']}")
        if st.button("创建新 revision") and feedback:
            try:
                result = api.post(
                    f"/agent/tasks/{task['task_id']}/refine", json={"feedback": feedback}
                )["data"]
                st.session_state.agent_task_id = result["task_id"]
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
    section_header("任务进度与版本", icon="🧭")
    try:
        tasks = api.get("/agent/tasks")["data"]
    except Exception as exc:
        show_error(exc)
        return
    if not tasks:
        empty_state("尚无命题任务，请先在“创建任务”中发起挑战。", icon="🤖")
        return
    labels = {
        item["task_id"]: (f"revision {item['revision']} · {item['status']} · {item['task_id'][:8]}")
        for item in tasks
    }
    active_id = st.session_state.get("agent_task_id")
    active_index = next((i for i, item in enumerate(tasks) if item["task_id"] == active_id), 0)
    selected = st.selectbox(
        "版本历史", list(labels), format_func=labels.get, index=max(0, active_index)
    )
    st.session_state.agent_task_id = selected
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
        st.progress(task["progress"] / 100, text=f"{task['stage']} · {task['status']}")
        status_badge(str(task["status"]))
        if task["status"] in {"pending", "running"} and st.button("中断任务"):
            try:
                api.post(f"/agent/tasks/{selected}/cancel")
            except Exception as exc:
                show_error(exc)
        for event in merged[-30:]:
            timeline_event(event["timestamp"], event["stage"], event["message"])
        if task["status"] in TERMINAL:
            _result(api, task)
            if selected_status not in TERMINAL:
                st.rerun()

    poll()


def render_agent(api: ApiClient) -> None:
    page_header(
        "AI Agent 智能命题",
        "把命题需求转化为经过多轮生成、执行验证和人工确认的完整题目。",
        icon="🤖",
        eyebrow="AI PROBLEM ARENA",
        variant="ai",
    )
    badges([("受控本地工具", "cyan"), ("多轮验证", "orange"), ("人工确认导入", "green")])
    selected_view = st.segmented_control(
        "功能",
        ["模型配置", "创建任务", "进度与结果"],
        default="模型配置",
        label_visibility="collapsed",
        key="agent_active_view",
    )
    if selected_view == "模型配置":
        _config(api)
    elif selected_view == "创建任务":
        _authoring_form(api)
    else:
        _task_monitor(api)
