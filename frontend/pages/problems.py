"""Problem browsing and complete problem editing forms."""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import (
    OPTIONAL_PLACEHOLDER,
    REQUIRED_PLACEHOLDER,
    render_status,
    show_error,
)
from frontend.components.submission_table import render_submission_table
from frontend.components.ui import badges, empty_state, info_card, page_header, section_header
from frontend.data_access import (
    invalidate_problem_cache,
    load_language_names,
    load_problem_summaries,
)
from frontend.models import build_problem_payload, validate_problem
from frontend.pages.agent import render_agent

PROBLEM_QUERY_KEY = "problem"


def problem_detail_actions(role: str | None) -> list[str]:
    """Return only actions authorized by the current role."""
    actions = ["编辑"] if role in {"user", "admin"} else []
    if role == "admin":
        actions.append("删除")
    return actions


def filter_problem_summaries(
    problems: Sequence[dict[str, Any]], query: str = "", difficulty: str = ""
) -> list[dict[str, Any]]:
    """Filter cached public problem metadata without another API request."""
    needle = query.strip().casefold()
    selected_difficulty = difficulty.strip()
    filtered = []
    for problem in problems:
        if selected_difficulty and str(problem.get("difficulty") or "") != selected_difficulty:
            continue
        searchable = " ".join(
            [
                str(problem.get("id") or ""),
                str(problem.get("title") or ""),
                str(problem.get("source") or ""),
                str(problem.get("author") or ""),
                *(str(tag) for tag in problem.get("tags") or []),
            ]
        ).casefold()
        if needle and needle not in searchable:
            continue
        filtered.append(dict(problem))
    return filtered


def _requested_problem_id() -> str:
    value = st.query_params.get(PROBLEM_QUERY_KEY, "")
    return str(value).strip()


def _open_problem(problem_id: str) -> None:
    st.query_params[PROBLEM_QUERY_KEY] = problem_id
    st.session_state.pop("problem_detail_action", None)


def _close_problem() -> None:
    st.session_state.pop("problem_detail_action", None)
    if PROBLEM_QUERY_KEY in st.query_params:
        del st.query_params[PROBLEM_QUERY_KEY]


def _select_detail_action(action: str) -> None:
    st.session_state["problem_detail_action"] = action


def _load_problem(api: ApiClient, problem_id: str) -> dict[str, Any] | None:
    try:
        return api.get(f"/problems/{problem_id}")["data"]
    except Exception as exc:
        show_error(exc)
        return None


def _render_problem_submission_tools(
    api: ApiClient, problem: dict[str, Any], user: dict[str, Any]
) -> None:
    section_header("快捷提交", icon="💻")
    try:
        languages = load_language_names(api.base_url, api)
    except Exception as exc:
        show_error(exc)
        languages = []
    if languages:
        with st.form(f"problem_submission_{problem['id']}"):
            language = st.selectbox("语言", languages)
            code = st.text_area(
                "代码",
                height=320,
                placeholder=REQUIRED_PLACEHOLDER,
                help="请按照题目的输入输出要求编写完整代码。",
            )
            submitted = st.form_submit_button("提交评测", type="primary")
        if submitted:
            if not code.strip():
                st.error("请输入代码。")
            else:
                try:
                    result = api.post(
                        "/submissions/",
                        json={
                            "problem_id": problem["id"],
                            "language": language,
                            "code": code,
                        },
                    )["data"]
                except Exception as exc:
                    show_error(exc)
                else:
                    st.session_state["selected_submission_id"] = result["submission_id"]
                    st.session_state["submission_polling"] = True
                    st.success(f"提交成功，编号：{result['submission_id']}")
                    render_status(result["status"])

    section_header("我的递交历史", icon="📜")
    try:
        history = api.get(
            "/submissions/",
            params={
                "user_id": int(user["id"]),
                "problem_id": problem["id"],
                "page": 1,
                "page_size": 5,
            },
        )["data"]
    except Exception as exc:
        show_error(exc)
        return
    submissions = history.get("submissions", [])
    if submissions:
        render_submission_table(submissions, key=f"problem_{problem['id']}")
    else:
        empty_state("你还没有提交过这道题。", icon="📭")


def render_problem_detail(
    api: ApiClient,
    problem_id: str,
    user: dict[str, Any],
) -> None:
    st.button("← 返回题目列表", on_click=_close_problem)
    with st.spinner("正在加载题目详情..."):
        problem = _load_problem(api, problem_id)
    if problem is None:
        return
    subtitle = " · ".join(
        value
        for value in (problem.get("source"), problem.get("author"))
        if value
    )
    page_header(
        problem["title"],
        subtitle or "阅读题目要求，设计并提交你的解法。",
        icon="🎯",
        eyebrow=f"PROBLEM {problem['id']}",
    )
    metadata = []
    if problem.get("difficulty"):
        metadata.append((str(problem["difficulty"]), "orange"))
    metadata.extend((str(tag), "orange") for tag in problem.get("tags", []))
    if metadata:
        badges(metadata)

    role = str(user.get("role") or "")
    actions = problem_detail_actions(role)
    if actions:
        action_columns = st.columns([1, 1, 6])
        action_columns[0].button(
            "编辑题目",
            type="primary",
            on_click=_select_detail_action,
            args=("编辑",),
        )
        if "删除" in actions:
            action_columns[1].button(
                "删除题目",
                on_click=_select_detail_action,
                args=("删除",),
            )

    time_col, memory_col = st.columns(2)
    with time_col:
        info_card("时间限制", f"{problem['time_limit']} 秒", icon="⏱️")
    with memory_col:
        info_card("内存限制", f"{problem['memory_limit']} MB", icon="💾")

    with st.container(border=True, key="problem_statement"):
        section_header("题目描述", icon="📖")
        st.markdown(problem["description"])
        section_header("输入说明", icon="📥")
        st.markdown(problem["input_description"])
        section_header("输出说明", icon="📤")
        st.markdown(problem["output_description"])
        section_header("约束", icon="📐")
        st.markdown(problem["constraints"])

        section_header("样例", icon="🧪")
        for index, sample in enumerate(problem["samples"], 1):
            st.markdown(f"#### 样例 {index}")
            left, right = st.columns(2)
            left.caption("输入")
            left.code(sample["input"], language=None)
            right.caption("输出")
            right.code(sample["output"], language=None)
        if problem.get("hint"):
            with st.expander("查看提示"):
                st.markdown(problem["hint"])

    detail_action = st.session_state.get("problem_detail_action")
    if detail_action == "编辑":
        section_header("编辑题目", icon="✏️")
        payload = _problem_form(problem, f"detail_edit_{problem['id']}")
        if payload is not None:
            errors = validate_problem(payload)
            if errors:
                for message in errors:
                    st.error(message)
            else:
                try:
                    api.put(f"/problems/{problem['id']}", json=payload)
                except Exception as exc:
                    show_error(exc)
                else:
                    invalidate_problem_cache()
                    st.success("题目保存成功。")
    elif detail_action == "删除" and role == "admin":
        section_header("确认删除", icon="🚨")
        st.warning("删除后无法恢复，请确认当前题目不再需要。")
        confirmed = st.checkbox(
            "我确认永久删除该题目。",
            key=f"detail_delete_confirm_{problem['id']}",
        )
        if st.button(
            "确认删除",
            type="primary",
            disabled=not confirmed,
            key=f"detail_delete_{problem['id']}",
        ):
            try:
                api.delete(f"/problems/{problem['id']}")
            except Exception as exc:
                show_error(exc)
            else:
                invalidate_problem_cache()
                _close_problem()
                st.session_state["problem_notice"] = "题目删除成功。"
                st.rerun()
    _render_problem_submission_tools(api, problem, user)


def render_problem_list(api: ApiClient, user: dict[str, Any]) -> None:
    requested_problem = _requested_problem_id()
    if requested_problem:
        render_problem_detail(api, requested_problem, user)
        return

    page_header(
        "挑战题库",
        "选择一道题目，阅读要求并开始你的下一次 AC。",
        icon="📚",
        eyebrow="CHALLENGE LIBRARY",
    )
    notice = st.session_state.pop("problem_notice", None)
    if notice:
        st.success(str(notice))
    try:
        with st.spinner("正在加载题目..."):
            problems = load_problem_summaries(api.base_url, api)
    except Exception as exc:
        show_error(exc)
        st.info("登录后查看题目列表。")
        return
    if not problems:
        empty_state("题库暂时为空，稍后再来挑战吧。", icon="📚")
        return
    section_header("筛选题目", icon="🔎")
    search_col, difficulty_col = st.columns([2, 1])
    search = search_col.text_input(
        "关键词",
        placeholder="输入题号、名称、标签或来源",
    )
    difficulties = sorted(
        {str(item.get("difficulty")) for item in problems if item.get("difficulty")}
    )
    selected_difficulty = difficulty_col.selectbox(
        "难度", ["全部难度", *difficulties]
    )
    filtered = filter_problem_summaries(
        problems,
        search,
        "" if selected_difficulty == "全部难度" else selected_difficulty,
    )
    badges([(f"共 {len(filtered)} 道题", "cyan")])
    if not filtered:
        empty_state("没有找到符合条件的题目，请调整筛选条件。", icon="🔍")
        return

    with st.container(key="problem_catalog"):
        header = st.columns([1.1, 3.2, 2.3, 1])
        header[0].markdown("**题号**")
        header[1].markdown("**题目名称**")
        header[2].markdown("**标签**")
        header[3].markdown("**难度**")
        for problem in filtered:
            row = st.columns([1.1, 3.2, 2.3, 1])
            row[0].write(problem["id"])
            row[1].button(
                str(problem["title"]),
                key=f"open_problem_{problem['id']}",
                on_click=_open_problem,
                args=(str(problem["id"]),),
                help=f"查看 {problem['title']} 的题目详情",
            )
            row[2].write(" · ".join(str(tag) for tag in problem.get("tags") or []) or "—")
            row[3].write(problem.get("difficulty") or "—")


def _pairs_editor(label: str, key: str, initial: list[dict[str, str]]) -> list[dict[str, str]]:
    count_key = f"{key}_count"
    st.session_state.setdefault(count_key, max(1, len(initial)))
    section_header(label, icon="🧩")
    add, remove = st.columns(2)
    if add.button("增加", key=f"{key}_add"):
        st.session_state[count_key] += 1
        st.rerun()
    if remove.button("删除末项", key=f"{key}_remove", disabled=st.session_state[count_key] <= 1):
        st.session_state[count_key] -= 1
        st.rerun()
    pairs = []
    for index in range(st.session_state[count_key]):
        default = initial[index] if index < len(initial) else {"input": "", "output": ""}
        left, right = st.columns(2)
        pairs.append(
            {
                "input": left.text_area(
                    f"{label} {index + 1} 输入",
                    default["input"],
                    key=f"{key}_{index}_in",
                    placeholder=REQUIRED_PLACEHOLDER,
                ),
                "output": right.text_area(
                    f"{label} {index + 1} 输出",
                    default["output"],
                    key=f"{key}_{index}_out",
                    placeholder=REQUIRED_PLACEHOLDER,
                ),
            }
        )
    return pairs


def _problem_form(initial: dict[str, Any] | None, prefix: str) -> dict[str, Any] | None:
    data = initial or {}
    problem_id = st.text_input(
        "题目 ID",
        data.get("id", ""),
        disabled=initial is not None,
        placeholder=REQUIRED_PLACEHOLDER,
    )
    title = st.text_input("标题", data.get("title", ""), placeholder=REQUIRED_PLACEHOLDER)
    description = st.text_area(
        "题面", data.get("description", ""), height=160, placeholder=REQUIRED_PLACEHOLDER
    )
    input_description = st.text_area(
        "输入说明", data.get("input_description", ""), placeholder=REQUIRED_PLACEHOLDER
    )
    output_description = st.text_area(
        "输出说明", data.get("output_description", ""), placeholder=REQUIRED_PLACEHOLDER
    )
    constraints = st.text_area(
        "约束", data.get("constraints", ""), placeholder=REQUIRED_PLACEHOLDER
    )
    samples = _pairs_editor("样例", f"{prefix}_samples", data.get("samples", []))
    testcases = _pairs_editor("测试点", f"{prefix}_tests", data.get("testcases", []))
    hint = st.text_area("提示", data.get("hint", ""), placeholder=OPTIONAL_PLACEHOLDER)
    source = st.text_input("来源", data.get("source", ""), placeholder=OPTIONAL_PLACEHOLDER)
    author = st.text_input("作者", data.get("author", ""), placeholder=OPTIONAL_PLACEHOLDER)
    difficulty = st.text_input(
        "难度", data.get("difficulty", ""), placeholder=OPTIONAL_PLACEHOLDER
    )
    tags = st.text_input(
        "标签",
        ", ".join(data.get("tags", [])),
        placeholder=OPTIONAL_PLACEHOLDER,
        help="使用英文逗号分隔",
    )
    time_limit = st.number_input(
        "时间限制（秒）", min_value=0.01, value=float(data.get("time_limit", 3.0))
    )
    memory_limit = st.number_input(
        "内存限制（MB）", min_value=1, value=int(data.get("memory_limit", 128))
    )
    if not st.button("保存题目", type="primary", key=f"{prefix}_save"):
        return None
    return build_problem_payload(
        {
            "id": problem_id,
            "title": title,
            "description": description,
            "input_description": input_description,
            "output_description": output_description,
            "constraints": constraints,
            "samples": samples,
            "testcases": testcases,
            "hint": hint,
            "source": source,
            "author": author,
            "difficulty": difficulty,
            "tags": tags.split(","),
            "time_limit": time_limit,
            "memory_limit": memory_limit,
        }
    )


def render_problem_management(api: ApiClient) -> None:
    page_header(
        "命题中心",
        "选择手动编辑完整题目，或使用 AI 辅助创建新题。",
        icon="✨",
        eyebrow="PROBLEM CREATION CENTER",
    )
    authoring_mode = st.segmented_control(
        "命题方式",
        ["普通命题", "AI 智能命题"],
        default="普通命题",
        key="problem_authoring_mode",
        label_visibility="collapsed",
    )
    if authoring_mode == "AI 智能命题":
        render_agent(api, embedded=True)
        return

    section_header("新建普通题目", icon="📝")
    payload = _problem_form(None, "problem_create")
    if payload is None:
        return
    errors = validate_problem(payload)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        api.post("/problems/", json=payload)
    except Exception as exc:
        show_error(exc)
    else:
        invalidate_problem_cache()
        st.success("题目保存成功。")
