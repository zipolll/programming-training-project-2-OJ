"""Problem browsing and complete problem editing forms."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error
from frontend.components.ui import badges, empty_state, info_card, page_header, section_header
from frontend.data_access import invalidate_problem_cache, load_problem_summaries
from frontend.models import build_problem_payload, validate_problem


def _load_problem(api: ApiClient, problem_id: str) -> dict[str, Any] | None:
    try:
        return api.get(f"/problems/{problem_id}")["data"]
    except Exception as exc:
        show_error(exc)
        return None


def render_problem_detail(api: ApiClient, problem_id: str) -> None:
    problem = _load_problem(api, problem_id)
    if problem is None:
        return
    section_header(
        f"{problem['id']} · {problem['title']}",
        icon="🎯",
    )
    meta = " · ".join(
        value
        for value in (
            problem.get("difficulty"),
            problem.get("author"),
            problem.get("source"),
        )
        if value
    )
    metadata = []
    if meta:
        metadata.append((meta, "cyan"))
    metadata.extend((str(tag), "orange") for tag in problem.get("tags", []))
    if metadata:
        badges(metadata)
    st.markdown(problem["description"])
    section_header("输入说明", icon="📥")
    st.markdown(problem["input_description"])
    section_header("输出说明", icon="📤")
    st.markdown(problem["output_description"])
    section_header("样例", icon="🧪")
    for index, sample in enumerate(problem["samples"], 1):
        left, right = st.columns(2)
        left.code(sample["input"], language=None)
        right.code(sample["output"], language=None)
        left.caption(f"样例 {index} 输入")
        right.caption(f"样例 {index} 输出")
    section_header("约束与限制", icon="⏱️")
    st.markdown(problem["constraints"])
    time_col, memory_col = st.columns(2)
    with time_col:
        info_card("时间限制", f"{problem['time_limit']} 秒", icon="⏱️")
    with memory_col:
        info_card("内存限制", f"{problem['memory_limit']} MB", icon="💾")
    if problem.get("hint"):
        st.info(problem["hint"])
    st.caption("隐藏测试点不会在题目详情页展示。")


def render_problem_list(api: ApiClient) -> None:
    page_header(
        "挑战题库",
        "选择一道题目，阅读要求并开始你的下一次 AC。",
        icon="📚",
        eyebrow="CHALLENGE LIBRARY",
    )
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
    badges([(f"共 {len(problems)} 道题", "cyan"), ("选择后自动加载详情", "green")])
    selected = st.selectbox(
        "选择题目查看详情",
        problems,
        format_func=lambda item: f"{item['id']} · {item['title']}",
    )
    render_problem_detail(api, selected["id"])


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
                    f"{label} {index + 1} 输入", default["input"], key=f"{key}_{index}_in"
                ),
                "output": right.text_area(
                    f"{label} {index + 1} 输出", default["output"], key=f"{key}_{index}_out"
                ),
            }
        )
    return pairs


def _problem_form(initial: dict[str, Any] | None, prefix: str) -> dict[str, Any] | None:
    data = initial or {}
    problem_id = st.text_input("题目 ID", data.get("id", ""), disabled=initial is not None)
    title = st.text_input("标题", data.get("title", ""))
    description = st.text_area("题面", data.get("description", ""), height=160)
    input_description = st.text_area("输入说明", data.get("input_description", ""))
    output_description = st.text_area("输出说明", data.get("output_description", ""))
    constraints = st.text_area("约束", data.get("constraints", ""))
    samples = _pairs_editor("样例", f"{prefix}_samples", data.get("samples", []))
    testcases = _pairs_editor("测试点", f"{prefix}_tests", data.get("testcases", []))
    hint = st.text_area("提示", data.get("hint", ""))
    source = st.text_input("来源", data.get("source", ""))
    author = st.text_input("作者", data.get("author", ""))
    difficulty = st.text_input("难度", data.get("difficulty", ""))
    tags = st.text_input("标签", ", ".join(data.get("tags", [])), help="使用英文逗号分隔")
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


def render_problem_management(api: ApiClient, is_admin: bool) -> None:
    page_header(
        "题目工坊",
        "创建完整题目、调整内容，管理员还可以执行删除操作。",
        icon="🛠️",
        eyebrow="PROBLEM WORKSHOP",
    )
    section_header("操作", icon="🎛️")
    options = ["新增", "编辑", "删除"] if is_admin else ["新增", "编辑"]
    mode = st.radio("操作", options, horizontal=True, label_visibility="collapsed")
    initial = None
    problem_id = ""
    if mode in {"编辑", "删除"}:
        problem_id = st.text_input("要操作的题目 ID")
        if not problem_id:
            return
        if mode == "删除":
            section_header("危险区域", icon="🚨")
            confirmed = st.checkbox("我确认永久删除该题目。")
            if st.button("删除题目", type="primary", disabled=not confirmed):
                try:
                    api.delete(f"/problems/{problem_id}")
                except Exception as exc:
                    show_error(exc)
                else:
                    invalidate_problem_cache()
                    st.success("题目删除成功。")
            return
        initial = _load_problem(api, problem_id)
        if initial is None:
            return
    payload = _problem_form(initial, f"problem_{mode}_{problem_id}")
    if payload is None:
        return
    errors = validate_problem(payload)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        if mode == "新增":
            api.post("/problems/", json=payload)
        else:
            api.put(f"/problems/{problem_id}", json=payload)
            _load_problem(api, problem_id)
    except Exception as exc:
        show_error(exc)
    else:
        invalidate_problem_cache()
        st.success("题目保存成功。")
