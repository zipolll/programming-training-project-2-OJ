"""Streamlit AI problem-authoring workflow."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error

TERMINAL = {"success", "error", "cancelled"}


def _config(api: ApiClient) -> None:
    st.subheader("模型配置")
    try:
        current = api.get("/agent/config")["data"]
    except Exception as exc:
        show_error(exc)
        return
    if not current.get("encryption_configured"):
        st.warning("后端尚未配置 OJ_CREDENTIAL_ENCRYPTION_KEY，基础 OJ 可用，但 AI 密钥不能保存。")
    if current.get("has_api_key"):
        st.caption(f"已保存密钥：{current.get('masked_api_key', '********')}（明文永不返回）")
    with st.form("agent-config"):
        provider_url = st.text_input("Provider URL", current.get("provider_url", ""))
        model_name = st.text_input("模型名称", current.get("model_name", ""))
        api_key = st.text_input("API Key（留空则保留）", type="password")
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
        currency = st.text_input("币种", current.get("currency", "USD"))
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
        payload = {
            "provider_url": provider_url,
            "model_name": model_name,
            "input_price_per_million_tokens": str(input_price),
            "output_price_per_million_tokens": str(output_price),
            "currency": currency,
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
    st.subheader("命题需求")
    try:
        problems = api.get("/problems/")["data"]
    except Exception:
        problems = []
    with st.form("agent-authoring"):
        knowledge = st.text_input("必须覆盖的知识点（逗号分隔）")
        difficulty = st.selectbox("目标难度", ["入门", "简单", "中等", "困难"])
        problem_type = st.text_input("题目类型", "算法题")
        algorithm = st.text_input("期望算法或复杂度")
        forbidden = st.text_input("禁止知识点（逗号分隔）")
        scale = st.text_input("数据规模")
        left, right = st.columns(2)
        time_limit = left.number_input("时间限制（秒）", 0.1, 60.0, 2.0)
        memory_limit = right.number_input("内存限制（MB）", 16, 4096, 128)
        background = st.text_input("背景偏好")
        testcase_count = st.number_input("测试点数量", 1, 100, 10)
        additional = st.text_area("补充要求")
        adapt = st.checkbox("基于已有题目改编")
        options = [""] + [item["id"] for item in problems]
        existing = st.selectbox("已有题目", options, disabled=not adapt)
        submitted = st.form_submit_button("创建命题任务")
    if submitted:
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
    usage = st.columns(4)
    usage[0].metric("输入 Token", task["input_tokens"])
    usage[1].metric("输出 Token", task["output_tokens"])
    usage[2].metric("总 Token", task["total_tokens"])
    suffix = "（估算）" if task["usage_estimated"] else ""
    usage[3].metric("费用", f"{task['cost']} {task['currency']} {suffix}")
    generated = task.get("final_problem") or task.get("draft")
    if generated:
        problem = generated["problem"]
        st.subheader(problem["title"])
        st.markdown(problem["description"])
        st.markdown(f"**输入**：{problem['input_description']}")
        st.markdown(f"**输出**：{problem['output_description']}")
        st.markdown(f"**约束**：{problem['constraints']}")
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
                st.success(f"已导入题目 {result['problem_id']}。")


def _task_monitor(api: ApiClient) -> None:
    st.subheader("任务进度与版本")
    try:
        tasks = api.get("/agent/tasks")["data"]
    except Exception as exc:
        show_error(exc)
        return
    if not tasks:
        st.info("尚无命题任务。")
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
            task = api.get(f"/agent/tasks/{selected}")["data"]
            events = api.get(
                f"/agent/tasks/{selected}/events",
                params={"after_id": st.session_state.get("agent_after_id", 0)},
            )["data"]
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
        if task["status"] in {"pending", "running"} and st.button("中断任务"):
            try:
                api.post(f"/agent/tasks/{selected}/cancel")
            except Exception as exc:
                show_error(exc)
        for event in merged[-30:]:
            st.caption(f"{event['timestamp']} · {event['stage']} · {event['message']}")
        if task["status"] in TERMINAL:
            _result(api, task)
            if selected_status not in TERMINAL:
                st.rerun()

    poll()


def render_agent(api: ApiClient) -> None:
    st.title("AI Agent 智能命题")
    st.caption("受控本地工具 · 多轮验证 · 人工确认导入")
    config_tab, author_tab, task_tab = st.tabs(["模型配置", "创建任务", "进度与结果"])
    with config_tab:
        _config(api)
    with author_tab:
        _authoring_form(api)
    with task_tab:
        _task_monitor(api)
