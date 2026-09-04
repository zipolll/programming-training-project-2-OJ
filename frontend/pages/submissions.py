"""Submission creation, listing, polling, results, and evaluation logs."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import (
    REQUIRED_PLACEHOLDER,
    render_status,
    show_error,
)
from frontend.components.pagination import (
    pagination_values,
    render_pagination,
    reset_pagination,
)
from frontend.components.submission_table import render_submission_table
from frontend.components.ui import badges, empty_state, page_header, section_header
from frontend.data_access import load_problem_summaries, load_submission_options
from frontend.errors import NetworkError
from frontend.models import should_poll, status_text
from frontend.session_cache import cached_for_session

MY_SUBMISSIONS = "我的提交"
STATUS_FILTERS = {
    "全部状态": None,
    "等待评测": "pending",
    "评测完成": "success",
    "评测异常": "error",
}


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
    st.session_state["selected_submission_id"] = submission_id
    st.session_state["submission_polling"] = False


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
        code = st.text_area(
            "代码",
            height=360,
            placeholder=REQUIRED_PLACEHOLDER,
            help="请按照题目的输入输出要求编写完整代码。",
        )
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

    def filters_changed() -> None:
        reset_pagination("submission_list")
        st.session_state.pop("selected_submission_id", None)

    try:
        problems = load_problem_summaries(api.base_url, api)
    except Exception as exc:
        show_error(exc)
        return
    problem_labels = {str(item["id"]): f"{item['id']} · {item['title']}" for item in problems}
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
    st.caption(f"共 {data.get('total', 0)} 条记录")
    submissions = data.get("submissions", [])
    if not submissions:
        empty_state("没有符合条件的提交。", icon="📭")
        render_pagination("submission_list", total=int(data.get("total", 0)))
        return
    badges([(f"共 {data.get('total', 0)} 条", "cyan"), (f"第 {page} 页", "orange")])
    render_submission_table(
        submissions,
        key="history",
        on_select=_select_submission,
    )
    render_pagination("submission_list", total=int(data.get("total", 0)))
    selected = st.session_state.get("selected_submission_id")
    if selected:
        section_header("提交详情", icon="🔍")
        if st.button("关闭详情"):
            st.session_state.pop("selected_submission_id", None)
            st.session_state["submission_polling"] = False
            st.rerun()
        render_submission_detail(api, str(selected), is_admin)


def render_visibility(api: ApiClient) -> None:
    page_header(
        "日志开放策略",
        "控制题目测试点日志是否向其他已登录用户公开。",
        icon="👁️",
        eyebrow="ADMIN VISIBILITY",
    )
    section_header("可见性设置", icon="🔐")
    problem_id = st.text_input("题目 ID", placeholder=REQUIRED_PLACEHOLDER)
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
