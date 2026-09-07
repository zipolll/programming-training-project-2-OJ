"""Problem browsing and complete problem editing forms."""

from collections.abc import Callable, Sequence
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.code_editor import render_code_submission
from frontend.components.common import (
    OPTIONAL_PLACEHOLDER,
    REQUIRED_PLACEHOLDER,
    show_error,
)
from frontend.components.layout import (
    cell_text,
    data_table,
    form_row,
    section_card,
    split_view,
    table_row,
)
from frontend.components.pagination import pagination_values, render_pagination
from frontend.components.submission_table import render_submission_table
from frontend.components.ui import (
    badges,
    empty_state,
    info_card,
    list_count,
    page_header,
    section_header,
)
from frontend.data_access import (
    invalidate_problem_cache,
    load_language_names,
    load_problem_detail,
    load_problem_summaries,
)
from frontend.models import (
    DIFFICULTY_LEVELS,
    OTHER_OPTION,
    PROBLEM_TYPES,
    build_problem_payload,
    catalogue_selection,
    resolve_catalogue_option,
    validate_problem,
)
from frontend.navigation import open_submission, restore_widget, save_widgets, update_route
from frontend.pages.agent import render_agent

PROBLEM_QUERY_KEY = "problem"
DIFFICULTY_TONES = {
    "入门": "green",
    "简单": "cyan",
    "中等": "orange",
    "困难": "red",
}


def problem_detail_actions(role: str | None) -> list[str]:
    """Return only actions authorized by the current role."""
    actions = ["提交", "编辑"] if role in {"user", "admin"} else []
    if role == "admin":
        actions.append("删除")
    return actions


def problem_metadata_items(problem: dict[str, Any]) -> list[tuple[str, str]]:
    """Build visually distinct difficulty and taxonomy badges for a problem."""
    items: list[tuple[str, str]] = []
    difficulty = str(problem.get("difficulty") or "").strip()
    if difficulty:
        items.append((f"难度 · {difficulty}", difficulty_tone(difficulty)))
    problem_type = str(problem.get("problem_type") or "").strip()
    if problem_type:
        items.append((f"题型 · {problem_type}", "cyan"))
    items.extend(
        (str(tag).strip(), "cyan")
        for tag in problem.get("tags") or []
        if str(tag).strip()
    )
    return items


def difficulty_tone(difficulty: Any) -> str:
    """Use a stable, distinct colour for each standard difficulty level."""
    return DIFFICULTY_TONES.get(str(difficulty or "").strip(), "purple")


def first_problem_tag(problem: dict[str, Any]) -> str:
    """Return only the first non-empty tag for compact catalogue display."""
    return next(
        (
            str(tag).strip()
            for tag in problem.get("tags") or []
            if str(tag).strip()
        ),
        "",
    )


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
                str(problem.get("problem_type") or ""),
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
    update_route(problem=problem_id, action=None)
    st.session_state.pop("problem_detail_action", None)
    st.session_state.pop("problem_submission_selected", None)


def _close_problem() -> None:
    st.session_state.pop("problem_detail_action", None)
    update_route(problem=None, action=None)


def _select_detail_action(action: str) -> None:
    update_route(action=action)
    if action:
        st.session_state["problem_detail_action"] = action
    else:
        st.session_state.pop("problem_detail_action", None)


def _load_problem(api: ApiClient, problem_id: str) -> dict[str, Any] | None:
    try:
        return load_problem_detail(api, problem_id)
    except Exception as exc:
        show_error(exc)
        return None


def _render_problem_submission_tools(
    api: ApiClient, problem: dict[str, Any], user: dict[str, Any]
) -> None:
    page_header(
        f"提交 · {problem['title']}",
        "选择语言并提交你的解法。",
        icon="⚡",
        eyebrow=f"PROBLEM {problem['id']}",
    )
    try:
        languages = load_language_names(api.base_url, api)
    except Exception as exc:
        show_error(exc)
        languages = []
    with split_view("submission_workspace", (2, 1)) as workspace:
        with workspace[0]:
            if languages:
                with section_card("代码与运行环境", key=f"submit_{problem['id']}", icon="💻"):
                    render_code_submission(
                        api, str(problem["id"]), languages, key=f"submit_{problem['id']}",
                    )
        with workspace[1], st.container(key="oj_recent_submissions"):
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
            list_count(int(history.get("total", len(submissions))))
            if submissions:
                render_submission_table(
                    submissions,
                    key=f"problem_{problem['id']}",
                    on_select=open_submission,
                    compact=True,
                )
            else:
                empty_state("你还没有提交过这道题。", icon="📭")


def render_problem_detail(
    api: ApiClient,
    problem_id: str,
    user: dict[str, Any],
    *, back_label: str = "← 返回题目列表",
) -> None:
    with st.spinner("正在加载题目详情..."):
        problem = _load_problem(api, problem_id)
    if problem is None:
        st.button(back_label, on_click=_close_problem)
        return
    role = str(user.get("role") or "")
    detail_action = st.query_params.get("action", "")
    if detail_action in {"提交", "编辑", "删除"}:
        st.button(
            "← 返回题目详情",
            on_click=_select_detail_action,
            args=("",),
        )
        if detail_action == "提交":
            _render_problem_submission_tools(api, problem, user)
            return
        if detail_action == "编辑" and role in {"user", "admin"}:
            page_header(
                f"编辑 · {problem['title']}",
                "修改后保存完整题目内容。",
                icon="✏️",
                eyebrow=f"PROBLEM {problem['id']}",
            )
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
            return
        if detail_action == "删除" and role == "admin":
            page_header(
                f"删除 · {problem['title']}",
                "请确认是否永久删除这道题目。",
                icon="🗑️",
                eyebrow=f"PROBLEM {problem['id']}",
            )
            st.warning("删除后无法恢复，请确认当前题目不再需要。")
            confirmed = st.checkbox(
                "我确认永久删除该题目。", key=f"detail_delete_confirm_{problem['id']}"
            )
            if st.button(
                "确认删除", type="primary", disabled=not confirmed,
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
            return

    st.button(back_label, on_click=_close_problem)
    actions = problem_detail_actions(role)
    page_header(problem["title"], "阅读题目要求，设计并提交你的解法。")
    with st.container(key="oj_problem_reading"):
        with st.container(key="oj_problem_facts"):
            with st.container(key="oj_problem_summary"):
                summary = st.columns(4, gap="medium")
                for column, label, value in zip(
                    summary,
                    ("题号", "难度", "时间限制", "内存限制"),
                    (problem["id"], problem.get("difficulty") or "—",
                     f"{problem['time_limit']} 秒", f"{problem['memory_limit']} MB"),
                    strict=True,
                ):
                    with column:
                        info_card(label, value)
            with st.container(key="oj_problem_credits"):
                source, author = st.columns(2, gap="medium")
                with source:
                    info_card("来源", problem.get("source") or "—")
                with author:
                    info_card("作者", problem.get("author") or "—")
            metadata = problem_metadata_items({**problem, "difficulty": ""})
            if metadata:
                badges(metadata)
            if actions:
                from frontend.components.bank_controls import render_add_to_bank

                with st.container(
                    key="oj_problem_actions", horizontal=True, horizontal_alignment="right",
                ):
                    st.button(
                        "去提交", type="primary", on_click=_select_detail_action, args=("提交",),
                    )
                    render_add_to_bank(api, str(problem["id"]))
                    with st.popover("更多", icon=":material/more_horiz:"):
                        st.button("编辑题目", on_click=_select_detail_action, args=("编辑",))
                        if "删除" in actions:
                            st.button("删除题目", on_click=_select_detail_action, args=("删除",))
        with st.container(border=False, key="problem_statement"):
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
    bank_notice = st.session_state.pop("bank_notice", None)
    if bank_notice:
        st.success(bank_notice)
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
    render_problem_catalogue(api, problems)


def render_problem_catalogue(
    api: ApiClient, problems: list[dict[str, Any]], *,
    key: str = "problem_list", selectable: bool = False,
    on_remove: Callable[[str], None] | None = None,
    show_count: bool = True,
    empty_message: str = "暂无题目。",
) -> list[str]:
    from frontend.components.bank_controls import prepare_selection

    if not problems and not selectable:
        if show_count:
            list_count(0)
        empty_state(empty_message, icon="📚")
        return []

    def filters_changed() -> None:
        save_widgets(f"{key}_search", f"{key}_difficulty", reset_page=key)

    restore_widget(f"{key}_search")

    with section_card("", key=f"{key}_filters", tone="toolbar"):
        search_col, difficulty_col = st.columns([4, 1])
        search = search_col.text_input(
            "关键词",
            placeholder="输入题号、名称、标签或来源",
            key=f"{key}_search",
            on_change=filters_changed,
            label_visibility="collapsed",
        )
        available_difficulties = {
            str(item.get("difficulty")).strip()
            for item in problems
            if str(item.get("difficulty") or "").strip()
        }
        difficulties = [
            *(
                difficulty
                for difficulty in DIFFICULTY_LEVELS
                if difficulty in available_difficulties
            ),
            *sorted(available_difficulties - set(DIFFICULTY_LEVELS)),
        ]
        restore_widget(f"{key}_difficulty", "全部难度", options=["全部难度", *difficulties])
        selected_difficulty = difficulty_col.selectbox(
            "难度", ["全部难度", *difficulties],
            key=f"{key}_difficulty",
            on_change=filters_changed,
            label_visibility="collapsed",
        )
    filtered = filter_problem_summaries(
        problems,
        search,
        "" if selected_difficulty == "全部难度" else selected_difficulty,
    )
    if show_count:
        list_count(len(filtered))
    if not filtered:
        empty_state(
            "没有找到符合条件的题目，请调整筛选条件。" if problems else empty_message,
            icon="🔍" if problems else "📚",
        )
        return []

    page, page_size = pagination_values(key)
    start = (page - 1) * page_size
    visible = filtered[start : start + page_size]
    selection_key = (
        prepare_selection(key, (page, search, selected_difficulty), visible) if selectable else ""
    )
    labels = ("题号", "题目", "难度")
    widths = (1.2, 5, 1)
    if selectable:
        labels = ("选择", *labels)
        widths = (0.6, *widths)
    if on_remove:
        labels = (*labels, "操作")
        widths = (*widths, 1)
    with data_table(labels, widths, key=f"{key}_table"):
        for problem in visible:
            with table_row(labels, widths, key=f"{key}_row_{problem['id']}") as row:
                if selectable:
                    row[0].checkbox(
                        f"选择 {problem['id']}", key=f"{selection_key}_item_{problem['id']}",
                        label_visibility="collapsed",
                    )
                    row = row[1:]
                with row[0]:
                    cell_text(problem["id"], tone="muted")
                row[1].button(
                    str(problem["title"]),
                    key=(f"open_problem_{problem['id']}" if key == "problem_list"
                         else f"{key}_open_{problem['id']}"),
                    on_click=_open_problem,
                    args=(str(problem["id"]),),
                    disabled=not problem.get("available", True),
                    help=f"查看 {problem['title']} 的题目详情",
                )
                with row[1]:
                    metadata = [str(problem.get("problem_type") or "").strip()]
                    metadata.extend(str(tag).strip() for tag in problem.get("tags") or [])
                    if any(metadata):
                        with st.container(key=f"oj_catalogue_meta_{key}_{problem['id']}"):
                            badges([(value, "gray") for value in dict.fromkeys(metadata) if value])
                difficulty = str(problem.get("difficulty") or "").strip()
                with row[2]:
                    if difficulty:
                        badges([(difficulty, difficulty_tone(difficulty))])
                    else:
                        cell_text("—", tone="muted")
                if on_remove:
                    with row[-1], st.popover("移出题库"):
                        st.caption("仅移除收录关系，不删除原题。")
                        if st.button("确认移出", key=f"{key}_remove_{problem['id']}"):
                            on_remove(str(problem["id"]))
    render_pagination(key, total=len(filtered))

    return [
        p["id"] for p in visible
        if selectable and st.session_state.get(f"{selection_key}_item_{p['id']}")
    ]


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


def _catalogue_select(
    container: Any,
    label: str,
    current: Any,
    options: list[str],
    *,
    key: str,
) -> str:
    """Render an optional dropdown with an explicit custom-value field."""
    selected = catalogue_selection(current, options, allow_empty=True)
    choices = ["", *options, OTHER_OPTION]
    choice = container.selectbox(
        label,
        choices,
        index=choices.index(selected),
        key=key,
        format_func=lambda value: "未设置" if value == "" else value,
    )
    other = ""
    if choice == OTHER_OPTION:
        current_value = str(current or "").strip()
        other = container.text_input(
            f"其它{label}",
            current_value if selected == OTHER_OPTION else "",
            key=f"{key}_other",
            placeholder=f"请输入自定义{label}",
        )
    return resolve_catalogue_option(choice, other)


def _problem_form(initial: dict[str, Any] | None, prefix: str) -> dict[str, Any] | None:
    data = initial or {}
    with section_card("基本信息", key=f"{prefix}_basic", icon="🪪"):
        with form_row(f"{prefix}_identity") as fields:
            problem_id = fields[0].text_input(
                "题目 ID", data.get("id", ""), disabled=initial is not None,
                placeholder=REQUIRED_PLACEHOLDER,
            )
            title = fields[1].text_input(
                "标题", data.get("title", ""), placeholder=REQUIRED_PLACEHOLDER,
            )
        with form_row(f"{prefix}_credits") as fields:
            source = fields[0].text_input(
                "来源", data.get("source", ""), placeholder=OPTIONAL_PLACEHOLDER,
            )
            author = fields[1].text_input(
                "作者", data.get("author", ""), placeholder=OPTIONAL_PLACEHOLDER,
            )
    with section_card("题面内容", key=f"{prefix}_statement", icon="📖"):
        description = st.text_area(
            "题面", data.get("description", ""), height=160, placeholder=REQUIRED_PLACEHOLDER
        )
        with form_row(f"{prefix}_io") as fields:
            input_description = fields[0].text_area(
                "输入说明", data.get("input_description", ""), placeholder=REQUIRED_PLACEHOLDER
            )
            output_description = fields[1].text_area(
                "输出说明", data.get("output_description", ""), placeholder=REQUIRED_PLACEHOLDER
            )
        with form_row(f"{prefix}_guidance") as fields:
            constraints = fields[0].text_area(
                "约束", data.get("constraints", ""), placeholder=REQUIRED_PLACEHOLDER
            )
            hint = fields[1].text_area(
                "提示", data.get("hint", ""), placeholder=OPTIONAL_PLACEHOLDER,
            )
    with section_card("样例与测试点", key=f"{prefix}_cases", icon="🧪"):
        samples = _pairs_editor("样例", f"{prefix}_samples", data.get("samples", []))
        testcases = _pairs_editor("测试点", f"{prefix}_tests", data.get("testcases", []))
    with section_card("分类与资源限制", key=f"{prefix}_limits", icon="⚙️"):
        difficulty_col, type_col = st.columns(2)
        difficulty = _catalogue_select(
            difficulty_col,
            "难度",
            data.get("difficulty", ""),
            DIFFICULTY_LEVELS,
            key=f"{prefix}_difficulty",
        )
        problem_type = _catalogue_select(
            type_col,
            "题型",
            data.get("problem_type", ""),
            PROBLEM_TYPES,
            key=f"{prefix}_problem_type",
        )
        tags = st.text_input(
            "标签",
            ", ".join(data.get("tags", [])),
            placeholder=OPTIONAL_PLACEHOLDER,
            help="使用英文逗号分隔",
        )
        with form_row(f"{prefix}_resources") as fields:
            time_limit = fields[0].number_input(
                "时间限制（秒）", min_value=0.01, value=float(data.get("time_limit", 3.0))
            )
            memory_limit = fields[1].number_input(
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
            "problem_type": problem_type,
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
    restore_widget("problem_authoring_mode", "普通命题", options=["普通命题", "AI 智能命题"])
    authoring_mode = st.segmented_control(
        "命题方式",
        ["普通命题", "AI 智能命题"],
        key="problem_authoring_mode",
        on_change=save_widgets,
        args=("problem_authoring_mode",),
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
