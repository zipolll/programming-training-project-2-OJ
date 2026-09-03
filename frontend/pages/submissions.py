"""Submission creation, listing, polling, results, and evaluation logs."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import render_status, show_error
from frontend.components.ui import badges, empty_state, page_header, section_header
from frontend.data_access import load_submission_options
from frontend.errors import NetworkError
from frontend.models import should_poll, status_text


def render_submit(api: ApiClient) -> None:
    page_header(
        "提交挑战",
        "选择题目和语言，提交代码并等待评测结果。",
        icon="⚡",
        eyebrow="READY TO JUDGE",
    )
    try:
        with st.spinner("正在加载题目和语言..."):
            problems, languages = load_submission_options(api)
    except Exception as exc:
        show_error(exc)
        return
    if not problems or not languages:
        empty_state("当前没有可提交的题目或语言。", icon="⌛")
        return
    badges([(f"{len(problems)} 道可选题", "cyan"), (" / ".join(languages), "orange")])
    section_header("代码与运行环境", icon="💻")
    with st.form("submission_form"):
        problem = st.selectbox(
            "题目", problems, format_func=lambda item: f"{item['id']} · {item['title']}"
        )
        language = st.selectbox("语言", languages)
        code = st.text_area("代码", height=360, help="请按照题目的输入输出要求编写完整代码。")
        submitted = st.form_submit_button("提交评测", type="primary")
    if not submitted:
        return
    if not code.strip():
        st.error("请输入代码。")
        return
    try:
        result = api.post(
            "/submissions/",
            json={"problem_id": problem["id"], "language": language, "code": code},
        )["data"]
    except Exception as exc:
        show_error(exc)
    else:
        st.session_state["selected_submission_id"] = result["submission_id"]
        st.session_state["submission_polling"] = True
        st.success(f"提交成功，编号：{result['submission_id']}")
        render_status(result["status"])


def _render_detail_data(data: dict[str, Any]) -> None:
    section_header(
        f"提交 #{data['submission_id']}",
        icon="🏁",
    )
    render_status(data.get("status"))
    if data.get("score") is not None:
        st.metric("得分", f"{data['score']} / {data.get('counts', '—')}")
    compile_info = data.get("compile_info")
    if compile_info:
        with st.expander("编译信息", expanded=compile_info.get("result") == "error"):
            st.code(compile_info.get("message") or compile_info.get("result"), language=None)
    run_info = data.get("run_info")
    if run_info:
        st.write(f"运行阶段：{run_info.get('result', '—')} · {run_info.get('message', '')}")
    if data.get("error_info"):
        with st.expander("评测错误", expanded=True):
            st.code(data["error_info"], language=None)


def _fetch_and_render_detail(api: ApiClient, submission_id: str) -> str | None:
    data = api.get(f"/submissions/{submission_id}")["data"]
    _render_detail_data(data)
    return data.get("status")


def _render_log(api: ApiClient, submission_id: str) -> None:
    section_header("测试点日志", icon="🔬")
    if not st.button("查看测试点日志", key=f"log_{submission_id}"):
        return
    try:
        data = api.get(f"/submissions/{submission_id}/log")["data"]
    except Exception as exc:
        show_error(exc)
        return
    details = data.get("details", [])
    if not details:
        empty_state("暂时没有测试点日志。", icon="🧪")
    else:
        rows = [
            {
                "测试点": item["id"],
                "结果": status_text(item["result"]),
                "时间（秒）": item["time"],
                "内存（MB）": item["memory"],
                "错误摘要": item.get("error_summary", ""),
            }
            for item in details
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def render_submission_detail(api: ApiClient, submission_id: str, is_admin: bool) -> None:
    polling = bool(st.session_state.get("submission_polling", False))

    if polling:

        @st.fragment(run_every=1.0)
        def poll_fragment() -> None:
            try:
                status = _fetch_and_render_detail(api, submission_id)
            except NetworkError as exc:
                st.session_state["submission_polling"] = False
                show_error(exc)
                st.warning("自动轮询已停止，请使用重试按钮。")
                return
            except Exception as exc:
                st.session_state["submission_polling"] = False
                show_error(exc)
                return
            if not should_poll(status):
                st.session_state["submission_polling"] = False
                st.rerun()

        poll_fragment()
    else:
        try:
            status = _fetch_and_render_detail(api, submission_id)
        except Exception as exc:
            show_error(exc)
            return
        if should_poll(status) and st.button("启动自动刷新"):
            st.session_state["submission_polling"] = True
            st.rerun()
        if st.button("刷新一次"):
            st.rerun()

    _render_log(api, submission_id)
    if is_admin:
        section_header("管理员操作", icon="🛡️")
        confirmed = st.checkbox("我确认重新评测该提交。", key=f"rejudge_confirm_{submission_id}")
        if st.button("重新评测", disabled=not confirmed, key=f"rejudge_{submission_id}"):
            try:
                result = api.put(f"/submissions/{submission_id}/rejudge")["data"]
            except Exception as exc:
                show_error(exc)
            else:
                st.session_state["submission_polling"] = True
                st.success(f"重新评测已开始：{result['status']}")
                st.rerun()


def render_submission_list(api: ApiClient, user: dict[str, Any], is_admin: bool) -> None:
    page_header(
        "评测战绩",
        "筛选历史提交，复盘每一次等待、通过与错误。",
        icon="📈",
        eyebrow="SUBMISSION HISTORY",
    )
    section_header("筛选条件", icon="🔎")
    left, middle, right = st.columns(3)
    problem_id = left.text_input("题目 ID 筛选")
    status = middle.selectbox("状态筛选", ["全部", "pending", "success", "error"])
    user_id = right.text_input(
        "用户 ID 筛选",
        value="" if is_admin else str(user["id"]),
        disabled=not is_admin,
    )
    page_size = st.selectbox("每页数量", [10, 20, 50])
    page = int(st.number_input("页码", min_value=1, value=1))
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if problem_id.strip():
        params["problem_id"] = problem_id.strip()
    if user_id.strip():
        if not user_id.strip().isdigit() or int(user_id) < 1:
            st.error("用户 ID 只能填写正整数。")
            return
        params["user_id"] = int(user_id)
    if status != "全部":
        params["status"] = status
    if "problem_id" not in params and "user_id" not in params:
        st.info("请至少填写题目 ID 或用户 ID。")
        return
    try:
        data = api.get("/submissions/", params=params)["data"]
    except Exception as exc:
        show_error(exc)
        return
    st.caption(f"共 {data.get('total', 0)} 条记录")
    submissions = data.get("submissions", [])
    if not submissions:
        empty_state("没有符合条件的提交。", icon="📭")
        return
    badges([(f"共 {data.get('total', 0)} 条", "cyan"), (f"第 {page} 页", "orange")])
    rows = [
        {
            "提交编号": item["submission_id"],
            "状态": status_text(item["status"]),
            "得分": item.get("score", "—"),
            "总分": item.get("counts", "—"),
        }
        for item in submissions
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    selected = st.selectbox("查看详情", [item["submission_id"] for item in submissions])
    st.session_state["selected_submission_id"] = selected
    render_submission_detail(api, selected, is_admin)


def render_visibility(api: ApiClient) -> None:
    page_header(
        "日志开放策略",
        "控制题目测试点日志是否向其他已登录用户公开。",
        icon="👁️",
        eyebrow="ADMIN VISIBILITY",
    )
    section_header("可见性设置", icon="🔐")
    problem_id = st.text_input("题目 ID")
    public_cases = st.toggle("向所有已登录用户公开测试点日志")
    confirmed = st.checkbox("我确认修改该题目的日志可见性。")
    if st.button("保存可见性", type="primary", disabled=not confirmed or not problem_id):
        try:
            result = api.put(
                f"/problems/{problem_id}/log_visibility",
                json={"public_cases": public_cases},
            )["data"]
        except Exception as exc:
            show_error(exc)
        else:
            visibility = "公开" if result["public_cases"] else "仅限有权限的用户查看"
            st.success(f"题目 {result['problem_id']} 的测试点日志已设为{visibility}。")
