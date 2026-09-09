"""One editor draft shared by form fields, reference checks and AI messages."""

import json
from copy import deepcopy
from uuid import uuid4

import streamlit as st

from frontend.components.common import show_error
from frontend.components.layout import cell_text, data_table, table_row
from frontend.components.ui import badges, status_tone
from frontend.models import status_text
from frontend.navigation import update_route


def working(task):
    key = f"agent_working_{task['task_id']}"
    saved = task.get("final_problem") or task.get("draft")
    state = st.session_state.get(key)
    if state is None:
        state = {
            "content": deepcopy(saved),
            "saved": deepcopy(saved),
            "seed": deepcopy(saved),
            "expected_hash": task.get("content_hash", ""),
            "epoch": 0,
        }
        st.session_state[key] = state
    elif state.get("expected_hash") != task.get("content_hash", "") and not dirty(state):
        state.update(
            content=deepcopy(saved),
            saved=deepcopy(saved),
            seed=deepcopy(saved),
            expected_hash=task.get("content_hash", ""),
            epoch=state["epoch"] + 1,
        )
    return state


def dirty(state):
    return state.get("content") != state.get("saved")


def navigate(**route):
    current = st.query_params.get("agent_task_id")
    state = st.session_state.get(f"agent_working_{current}", {})
    if dirty(state) and (
        route.get("agent_task_id", current) != current
        or route.get("agent_active_view", "任务详情") != "任务详情"
    ):
        st.session_state["agent_pending_navigation"] = route
    else:
        update_route(**route)


@st.dialog("尚有未保存的修改")
def navigation_dialog():
    st.write("离开后将放弃当前页面草稿。请先保存，或选择放弃修改后离开。")
    stay, leave = st.columns(2)
    stay.button("留在当前页面", on_click=_stay_on_page)
    leave.button("放弃修改并离开", on_click=_discard_and_leave)


def _stay_on_page():
    st.session_state.pop("agent_pending_navigation", None)


def _discard_and_leave():
    tid = st.query_params.get("agent_task_id")
    st.session_state.pop(f"agent_working_{tid}", None)
    route = st.session_state.pop("agent_pending_navigation")
    update_route(**route)


def browser_guard(state):
    component = st.components.v2.component(
        "oj_editor_unload",
        html="<span aria-hidden='true'></span>",
        css=":host {display:none}",
        js="""export default function({data}) {
            const guard = (event) => {
                if (data.dirty) {event.preventDefault(); event.returnValue='';}
            };
            window.addEventListener('beforeunload', guard);
            return () => window.removeEventListener('beforeunload', guard);
        }""",
    )
    component(data={"dirty": dirty(state)}, key="agent_unload_guard")


def request(api, task, state, action, feedback=""):
    signature = json.dumps(
        [action, state["content"], feedback, state["expected_hash"]], sort_keys=True
    )
    pending = state.get("submission")
    if not pending or pending["signature"] != signature:
        pending = {"signature": signature, "id": str(uuid4())}
        state["submission"] = pending
    payload = {"generated": state["content"]}
    if action in ("save-content", "versions"):
        payload["expected_hash"] = state["expected_hash"]
        check = state.get("check")
        if check and check.get("input_draft") == state["content"]:
            payload["check_id"] = check["task_id"]
        if action == "versions":
            payload.update(force_new=True, request_id=pending["id"])
    else:
        payload["request_id"] = pending["id"]
        if action == "refine":
            payload = {
                "workspace_draft": state["content"],
                "feedback": feedback,
                "request_id": pending["id"],
            }
    try:
        result = api.post(f"/agent/tasks/{task['task_id']}/{action}", json=payload)["data"]
    except Exception as exc:
        show_error(exc)
        return
    state.pop("submission", None)
    if action in ("quick-validate", "refine"):
        state["job"] = result["task_id"]
        st.session_state.pop("agent_poll_completed_task", None)
        state["seed"] = deepcopy(state["content"])
        state["epoch"] += 1
        if action == "quick-validate":
            # A new check replaces the previous result instead of stacking on it.
            state.pop("check", None)
    else:
        state["saved"] = deepcopy(state["content"])
        st.session_state["agent_notice"] = (
            "已另存为新版本。" if action == "versions" else "已保存当前版本。"
        )
        st.session_state.pop(f"agent_working_{result['task_id']}", None)
        update_route(agent_task_id=result["task_id"], agent_workspace_mode="编辑")


def receive_job(api, task, state, record):
    job_id = state.get("job")
    recovering = not job_id
    if not job_id:
        # Recover background work completed since this version was last saved.
        for attempt in reversed(record.get("attempts", [])):
            if (
                attempt.get("base_task_id") == task["task_id"]
                and attempt.get("workspace_kind")
                and attempt["task_id"] not in state.get("received_jobs", [])
                and (
                    attempt["status"] in ("pending", "running")
                    or (
                        not dirty(state)
                        and attempt.get("updated_at", "") > task.get("updated_at", "")
                    )
                )
            ):
                job_id = attempt["task_id"]
                state["job"] = job_id
                break
    if not job_id:
        return
    try:
        job = api.get(f"/agent/tasks/{job_id}")["data"]
    except Exception as exc:
        show_error(exc)
        return
    if recovering and not dirty(state) and job.get("input_draft"):
        state.update(
            content=deepcopy(job["input_draft"]),
            seed=deepcopy(job["input_draft"]),
            epoch=state["epoch"] + 1,
        )
    if job["status"] in ("pending", "running"):
        state["job_kind"] = job.get("workspace_kind")
        return
    state.pop("job", None)
    state.pop("job_kind", None)
    state.setdefault("received_jobs", []).append(job_id)
    if job.get("workspace_kind") == "check" and job.get("validation_report"):
        state["check"] = job
    elif job.get("workspace_kind") == "refine" and job["status"] == "success" and job.get("draft"):
        state.update(
            content=deepcopy(job["draft"]), seed=deepcopy(job["draft"]), epoch=state["epoch"] + 1
        )
        st.session_state["agent_notice"] = "AI 修改已更新到页面草稿，请选择保存或另存。"
    else:
        st.session_state["agent_job_error"] = (
            job.get("safe_error_message") or "本次执行未完成，页面草稿已保留。"
        )


def validation_result(state):
    if state.get("job") and state.get("job_kind") == "check":
        st.caption("正在验证当前草稿，完成后结果会显示在这里。")
        return
    check = state.get("check")
    if not check:
        return
    if check.get("input_draft") != state["content"]:
        st.caption("内容已变化，上次验证结果已失效。")
        return
    report = check["validation_report"]
    with st.expander("本次验证结果", expanded=True):
        if report["blocking_errors"]:
            st.error("参考程序未通过全部样例和测试点。")
        else:
            st.success("参考程序已通过全部样例和测试点。验证未保存题目。")
        for evidence_index, evidence in enumerate(report.get("tool_evidence", [])):
            result = evidence["result"]
            st.markdown(
                "**公开样例**" if evidence["tool"] == "validate_sample_outputs" else "**测试点**"
            )
            if result.get("compile_info"):
                st.code(str(result["compile_info"]), language=None)
            cases = result.get("testcases")
            if cases:
                labels = ("测试点", "结果", "时间", "内存", "评测信息")
                widths = (0.7, 1.7, 1, 1, 2)
                table_key = f"agent_check_{check['task_id']}_{evidence_index}"
                with data_table(labels, widths, key=table_key):
                    for item in cases:
                        with table_row(labels, widths, key=f"{table_key}_{item['id']}") as row:
                            with row[0]:
                                cell_text(item["id"], emphasis=True)
                            with row[1]:
                                badges([(status_text(item["result"]), status_tone(item["result"]))])
                            with row[2]:
                                cell_text(
                                    "—" if item["result"] == "CE" else f"{item['time']:.3f} 秒"
                                )
                            with row[3]:
                                cell_text(
                                    "—" if item["result"] == "CE" else f"{item['memory']:.2f} MB"
                                )
                            with row[4]:
                                cell_text(item.get("error_summary") or "—", tone="muted")
