"""Submission creation, listing, polling, results, and evaluation logs."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.code_editor import code_language, render_code_submission
from frontend.components.common import (
    show_error,
)
from frontend.components.layout import cell_text, data_table, section_card, table_row
from frontend.components.pagination import (
    pagination_values,
    render_pagination,
)
from frontend.components.submission_table import render_submission_table
from frontend.components.ui import (
    badges,
    empty_state,
    list_count,
    page_header,
    section_header,
    status_tone,
)
from frontend.data_access import load_problem_summaries, load_submission_options
from frontend.errors import NetworkError
from frontend.models import should_poll, status_text
from frontend.navigation import restore_widget, save_widgets, update_route
from frontend.session_cache import cached_for_session

MY_SUBMISSIONS = "我的提交"
STATUS_FILTERS = {
    "全部状态": None,
    "等待评测": "pending",
    "评测完成": "success",
    "评测异常": "error",
}
SUBMISSION_QUERY_KEY = "submission"


def resolve_submission_user_id(
    selection: str, users: list[dict[str, Any]], own_user_id: int
) -> int | None:
    """Resolve an admin username selection without sending usernames to the API."""
    if selection == MY_SUBMISSIONS:
        return own_user_id
    normalized = selection.strip().casefold()
    for candidate in users:
        if str(candidate.get("username") or "").casefold() == normalized:
            return int(candidate["user_id"])
    return None


def _select_submission(submission_id: str) -> None:
    update_route(submission=submission_id)


def _close_submission() -> None:
    st.session_state["submission_polling"] = False
    update_route(submission=None)


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
    problem_labels = {str(item["id"]): f"{item['id']} · {item['title']}" for item in problems}
    restore_widget("submission_problem", next(iter(problem_labels)), options=problem_labels)
    with section_card("代码与运行环境", key="submission_code", icon="💻"):
        problem_id = st.selectbox(
            "题目", list(problem_labels), format_func=problem_labels.get,
            key="submission_problem", on_change=save_widgets, args=("submission_problem",),
        )
        render_code_submission(api, problem_id, languages, key="submission")


def _render_detail_data(data: dict[str, Any]) -> None:
    status = str(data.get("status") or "")
    finished = "已完成评测" if status in {"success", "error"} else "评测进行中"
    if data.get("result") == "CE":
        finished = "编译错误"
    elif status == "error":
        finished = "评测异常"
    summary = st.columns(3)
    summary[0].metric("评测状态", finished)
    summary[1].metric("得分", data.get("score") if data.get("score") is not None else "—")
    summary[2].metric("总分", data.get("counts") if data.get("counts") is not None else "—")
    compile_info = data.get("compile_info")
    if compile_info:
        with st.expander("编译信息", expanded=compile_info.get("result") == "error"):
            st.code(compile_info.get("message") or compile_info.get("result"), language=None)
    if data.get("error_info"):
        with st.expander("评测错误", expanded=True):
            st.code(data["error_info"], language=None)


def _fetch_and_render_detail(api: ApiClient, submission_id: str) -> dict[str, Any]:
    data = api.get(f"/submissions/{submission_id}")["data"]
    _render_detail_data(data)
    return data


def _render_log(api: ApiClient, submission_id: str) -> None:
    section_header("测试点日志", icon="🔬")
    try:
        data = api.get(f"/submissions/{submission_id}/log")["data"]
    except Exception as exc:
        show_error(exc)
        return
    details = data.get("details", [])
    list_count(len(details))
    if not details:
        empty_state("暂时没有测试点日志。", icon="🧪")
    else:
        labels = ("测试点", "结果", "时间", "内存", "评测信息")
        widths = (.7, 1.7, 1, 1, 2)
        with data_table(labels, widths, key=f"testcases_{submission_id}"):
            for item in details:
                with table_row(
                    labels, widths, key=f"testcase_{submission_id}_{item['id']}"
                ) as row:
                    with row[0]:
                        cell_text(item["id"], emphasis=True)
                    result = str(item["result"])
                    with row[1]:
                        badges([(status_text(result), status_tone(result))])
                    with row[2]:
                        cell_text("—" if result == "CE" else f"{item['time']:.3f} 秒")
                    with row[3]:
                        cell_text("—" if result == "CE" else f"{item['memory']:.2f} MB")
                    with row[4]:
                        cell_text(item.get("error_summary") or "—", tone="muted")


def render_submission_detail(
    api: ApiClient,
    submission_id: str,
    is_admin: bool,
    *,
    show_heading: bool = False,
) -> None:
    try:
        data = api.get(f"/submissions/{submission_id}")["data"]
    except Exception as exc:
        show_error(exc)
        if isinstance(exc, NetworkError) and st.button("重试加载"):
            st.rerun()
        return
    language = str(data.get("language") or "未知语言")
    display_language = {"cpp": "C++", "python": "Python"}.get(language, language)
    badges([(f"提交语言 · {display_language}", "blue")])
    paused_key = f"submission_paused_{submission_id}"
    pending = should_poll(data.get("status"))
    interval = 1.0 if pending and not st.session_state.get(paused_key) else None

    @st.fragment(run_every=interval)
    def status_panel() -> None:
        try:
            latest = (
                api.get(f"/submissions/{submission_id}")["data"]
                if pending and not st.session_state.get(paused_key) else data
            )
        except Exception as exc:
            st.session_state[paused_key] = True
            st.session_state[f"{paused_key}_error"] = str(exc)
            st.rerun()
        _render_detail_data(latest)
        if pending and not should_poll(latest.get("status")):
            st.rerun()

    status_panel()
    if st.session_state.get(paused_key):
        st.warning("自动刷新已暂停：" + st.session_state.get(f"{paused_key}_error", "网络异常"))
        if st.button("重试加载", key=f"retry_{submission_id}"):
            st.session_state[paused_key] = False
            st.rerun()
    with st.expander("查看提交代码", expanded=False, key=f"source_{submission_id}",
                     on_change="rerun"):
        st.code(str(data.get("code") or ""), language=code_language(language), line_numbers=True)
    if not pending:
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
    requested_submission = str(st.query_params.get(SUBMISSION_QUERY_KEY, "")).strip()
    if requested_submission:
        st.button("← 返回提交记录", on_click=_close_submission)
        if not requested_submission.isdecimal() or int(requested_submission) < 1:
            st.error("提交编号无效，请返回提交记录重新选择。")
            return
        page_header(
            f"评测详情 #{requested_submission}",
            "查看本次提交的得分与各测试点结果。",
            icon="🏁",
            eyebrow="JUDGE DETAILS",
        )
        render_submission_detail(api, requested_submission, is_admin)
        return
    page_header(
        "评测战绩",
        "筛选历史提交，复盘每一次等待、通过与错误。",
        icon="📈",
        eyebrow="SUBMISSION HISTORY",
    )

    def filters_changed() -> None:
        save_widgets(
            "submission_problem_filter_v2", "submission_status_filter_v2",
            "submission_username_filter_admin", reset_page="submission_list",
        )

    try:
        problems = load_problem_summaries(api.base_url, api)
    except Exception as exc:
        show_error(exc)
        return
    problem_labels = {str(item["id"]): f"{item['id']} · {item['title']}" for item in problems}
    restore_widget("submission_problem_filter_v2", "", options=["", *problem_labels])
    restore_widget("submission_status_filter_v2", "全部状态", options=STATUS_FILTERS)
    with section_card("筛选条件", key="submission_filters", icon="🔎", tone="toolbar"):
        filter_columns = st.columns(3 if is_admin else 2)
        problem_id = filter_columns[0].selectbox(
            "题目",
            ["", *problem_labels],
            format_func=lambda value: "全部题目" if not value else problem_labels[value],
            key="submission_problem_filter_v2",
            on_change=filters_changed,
        )
        status_label = filter_columns[1].selectbox(
            "状态",
            list(STATUS_FILTERS),
            key="submission_status_filter_v2",
            on_change=filters_changed,
        )
        own_user_id = int(user["id"])
        user_id: int | None = own_user_id
        if is_admin:
            try:
                user_result = cached_for_session(
                    "submission_filter_users",
                    lambda: api.get("/users/", params={"page": 1, "page_size": 1000})[
                        "data"
                    ],
                )
            except Exception as exc:
                show_error(exc)
                return
            users = list(user_result.get("users", []))
            usernames = [str(item["username"]) for item in users]
            restore_widget("submission_username_filter_admin", MY_SUBMISSIONS)
            selected_username = filter_columns[2].selectbox(
                "用户",
                [MY_SUBMISSIONS, *usernames],
                key="submission_username_filter_admin",
                accept_new_options=True,
                help="可从列表选择，也可以直接输入完整用户名。",
                on_change=filters_changed,
            )
            user_id = resolve_submission_user_id(selected_username, users, own_user_id)
            if user_id is None:
                st.error("未找到该用户，请检查用户名。")
                return

    page, page_size = pagination_values("submission_list")
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "user_id": user_id,
    }
    if problem_id:
        params["problem_id"] = problem_id
    status = STATUS_FILTERS[status_label]
    if status:
        params["status"] = status
    try:
        data = api.get("/submissions/", params=params)["data"]
    except Exception as exc:
        show_error(exc)
        return
    list_count(int(data.get("total", 0)))
    submissions = data.get("submissions", [])
    if not submissions:
        empty_state("没有符合条件的提交。", icon="📭")
        render_pagination("submission_list", total=int(data.get("total", 0)))
        return
    render_submission_table(
        submissions,
        key="history",
        on_select=_select_submission,
    )
    render_pagination("submission_list", total=int(data.get("total", 0)))
