"""Prompt-first authoring, grouped history, and a versioned editing workspace."""

import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import show_error
from frontend.components.layout import cell_text, data_table, table_row
from frontend.components.pagination import pagination_values, render_pagination
from frontend.components.ui import badges, empty_state, list_count, section_header
from frontend.data_access import invalidate_problem_cache, load_problem_summaries
from frontend.models import DIFFICULTY_LEVELS, PROBLEM_TYPES
from frontend.navigation import restore_widget, save_widgets, update_route

STATUS = {
    "pending": "排队中",
    "running": "进行中",
    "success": "已完成",
    "error": "失败",
    "cancelled": "已停止",
    "draft": "待验证",
}
OPERATIONS = {
    "generate": "首次出题",
    "refine": "AI 修改",
    "retry": "重试",
    "edit": "手动编辑",
    "validate": "验证",
}
STAGES = {
    "queued": "等待开始",
    "requirement_analysis": "理解需求",
    "retrieve_context": "检索参考",
    "design_problem": "设计题目",
    "generate_solution": "生成解法",
    "generate_testcases": "生成测试点",
    "validate_schema": "检查题目格式",
    "execute_reference": "运行参考程序",
    "validate_testcases": "验证测试点",
    "review_quality": "检查质量",
    "revise": "修复验证问题",
    "finalize": "验证完成",
    "error": "执行失败",
    "interrupted": "服务重启中断",
    "cancelled": "已停止",
    "awaiting_validation": "等待验证",
}
EXAMPLES = {
    "算法入门": "出一道适合初学者的二分查找题，背景是寻找宝藏。",
    "专项练习": "出一道需要前缀和的中等难度题，包含负数和边界测试。",
    "趣味情境": "以校园食堂排队为背景，出一道考查队列的题目，并提供清晰的样例解释。",
}
LABELS = {
    "required_knowledge": "知识点",
    "difficulty": "难度",
    "problem_type": "题型",
    "expected_algorithm": "算法 / 复杂度",
    "forbidden_knowledge": "禁止知识点",
    "data_scale": "数据规模",
    "time_limit": "时间限制（秒）",
    "memory_limit": "内存限制（MB）",
    "testcase_count": "测试点数量",
    "background_preference": "背景偏好",
    "additional_requirements": "补充要求",
    "existing_problem_id": "改编题目",
}

ERRORS = {
    'model_timeout': '模型响应超时，可以重试或在模型配置中延长超时。',
    'model_connection_failed': '暂时无法连接模型服务，请检查连接后重试。',
    'model_unauthorized': '模型服务拒绝了当前密钥，请更新模型配置后重试。',
    'model_rate_limited': '模型服务请求过于频繁，请稍后重试。',
    'model_server_error': '模型服务暂时不可用，请稍后重试。',
    'model_request_rejected': '模型服务拒绝了请求，请检查模型配置与输入要求。',
    'invalid_model_response': '模型返回的内容无法解析，请重试生成。',
    'invalid_structured_output': '模型返回的题目格式不完整，请重试生成。',
    'validation_failed': '题目未通过验证。可手动修正后验证，或让 AI 继续修改。',
    'service_restarted': '服务重启中断了本次任务。历史内容已保留，可以重试。',
}


def task_error(task: dict) -> str:
    return ERRORS.get(task.get('error_code'), task.get('safe_error_message') or '')


def task_status(task: dict) -> str:
    return "draft" if task.get("stage") == "awaiting_validation" else task["status"]


def open_task(task_id: str, *, edit: bool = False) -> None:
    if edit:
        st.session_state['agent_compact_pane'] = '题目'
    update_route(
        agent_active_view="任务详情",
        agent_task_id=task_id,
        agent_workspace_mode="编辑" if edit else "预览",
    )


def _select_version() -> None:
    open_task(st.session_state.agent_version_selection)


def _post(api: ApiClient, path: str, payload: dict | None = None) -> None:
    if path == "/agent/tasks":
        signature = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        previous = st.session_state.get("agent_create_submission")
        if not previous or previous["signature"] != signature:
            previous = {"signature": signature, "id": str(uuid4())}
            st.session_state["agent_create_submission"] = previous
        payload = {**(payload or {}), "request_id": previous["id"]}
    try:
        result = api.post(path, json=payload or {})["data"]
    except Exception as exc:
        show_error(exc)
    else:
        if path == "/agent/tasks":
            st.session_state.pop("agent_create_submission", None)
        open_task(result["task_id"])
        st.rerun()


def _seed(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _set_value(key: str, value: Any) -> None:
    st.session_state[key] = value


def _clear_condition(prefix: str, name: str, empty: Any) -> None:
    st.session_state[f"{prefix}_{name}"] = empty
    if name == "existing_problem_id":
        st.session_state[f"{prefix}_adapt_existing"] = False


def requirement_inputs(api: ApiClient, prefix: str, initial: dict | None = None) -> dict:
    """Only return intentional settings; absent numerical limits remain AI-selected."""
    data = initial or {}
    _seed(f"{prefix}_prompt", data.get("prompt", ""))
    prompt = st.text_area(
        "描述你想出的题目",
        key=f"{prefix}_prompt",
        height=150,
        placeholder="例如：出一道适合初学者的二分查找题，背景是寻找宝藏。",
    )
    payload: dict[str, Any] = {"prompt": prompt.strip()} if prompt.strip() else {}
    fields = st.columns([2, 1, 1])
    values: dict[str, Any] = {}
    _seed(f"{prefix}_required_knowledge", "，".join(data.get("required_knowledge", [])))
    knowledge = fields[0].text_input(
        "知识点",
        key=f"{prefix}_required_knowledge",
        placeholder="AI 决定；多个知识点用逗号分隔",
    )
    values["required_knowledge"] = [
        x.strip() for x in knowledge.replace("，", ",").split(",") if x.strip()
    ]
    for column, name, options in (
        (fields[1], "difficulty", DIFFICULTY_LEVELS),
        (fields[2], "problem_type", PROBLEM_TYPES),
    ):
        selected = data.get(name, "")
        _seed(f"{prefix}_{name}", selected)
        available = list(
            dict.fromkeys(["", *options, selected, st.session_state.get(f"{prefix}_{name}", "")])
        )
        values[name] = (
            column.selectbox(
                LABELS[name],
                available,
                key=f"{prefix}_{name}",
                format_func=lambda x: x or "AI 决定",
                accept_new_options=True,
            )
            or ""
        )
    with st.expander("更多设置", expanded=False):
        for name in (
            "expected_algorithm",
            "forbidden_knowledge",
            "data_scale",
            "background_preference",
            "additional_requirements",
        ):
            initial_value = data.get(name, "")
            if isinstance(initial_value, list):
                initial_value = "，".join(initial_value)
            _seed(f"{prefix}_{name}", initial_value)
            value = st.text_input(LABELS[name], key=f"{prefix}_{name}", placeholder="AI 决定")
            values[name] = (
                [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]
                if name == "forbidden_knowledge"
                else value.strip()
            )
        columns = st.columns(3)
        for col, name, minimum, maximum in (
            (columns[0], "time_limit", 0.1, 60.0),
            (columns[1], "memory_limit", 16, 4096),
            (columns[2], "testcase_count", 3, 100),
        ):
            value = data.get(name)
            if value is not None:
                value = float(value) if name == "time_limit" else int(value)
                # Older requests allowed one or two testcases; keep them viewable unchanged.
                if name == 'testcase_count':
                    minimum = min(minimum, value)
            _seed(f"{prefix}_{name}", value)
            values[name] = col.number_input(
                LABELS[name],
                min_value=minimum,
                max_value=maximum,
                value=None,
                key=f"{prefix}_{name}",
                placeholder="AI 决定",
            )
        _seed(f"{prefix}_adapt_existing", bool(data.get("adapt_existing")))
        adapt = st.checkbox("基于已有题目改编", key=f"{prefix}_adapt_existing")
        if adapt:
            try:
                problems = load_problem_summaries(api.base_url, api)
            except Exception as exc:
                show_error(exc)
                problems = []
            titles = {p["id"]: f"{p['id']} · {p['title']}" for p in problems}
            _seed(f"{prefix}_existing_problem_id", data.get("existing_problem_id") or "")
            previous_id = st.session_state[f'{prefix}_existing_problem_id']
            if previous_id and previous_id not in titles:
                titles[previous_id] = f'{previous_id}（原题不可用）'
                st.warning('原改编题目已不可用，重新生成前请选择另一道题。')
            values["existing_problem_id"] = st.selectbox(
                "改编题目",
                ["", *titles],
                key=f"{prefix}_existing_problem_id",
                format_func=lambda x: titles.get(x, "选择题目"),
            )
            payload["adapt_existing"] = True
    payload.update(
        {
            key: value
            for key, value in values.items()
            if value is not None and value != "" and value != []
        }
    )
    settings = [(key, value) for key, value in payload.items() if key in LABELS]
    if settings:
        st.caption("固定条件优先于文字要求；点击条件可清除。")
        with st.container(horizontal=True, key=f"{prefix}_conditions"):
            for name, value in settings:
                label = "、".join(value) if isinstance(value, list) else str(value)
                st.button(
                    f"{LABELS[name]}：{label[:40]}{'…' if len(label) > 40 else ''} ×",
                    key=f"{prefix}_clear_{name}",
                    help=label,
                    on_click=_clear_condition,
                    args=(prefix, name, None if isinstance(value, (int, float)) else ""),
                )
    return payload


def authoring_form(api: ApiClient) -> None:
    try:
        config = api.get("/agent/config")["data"]
    except Exception as exc:
        show_error(exc)
        return
    ready = bool(config.get("configured") and config.get("has_api_key"))
    st.caption(
        f"当前模型：{config.get('model_name', '尚未配置')} · "
        + ("已配置，可在模型配置中测试连接" if ready else "请先完成模型配置")
    )
    section_header("从一个想法开始")
    st.caption("用一段话描述需求，或指定几个条件，让 AI 完成题面、参考解法和测试数据。")
    draft = st.session_state.get("agent_new_draft", {})
    prefix = f"agent_new_{st.session_state.get('agent_composer_id', 'initial')}"
    with st.container(horizontal=True):
        for label, example in EXAMPLES.items():
            st.button(
                label,
                key=f"{prefix}_example_{label}",
                on_click=_set_value,
                args=(f"{prefix}_prompt", example),
            )
    with st.container(key="oj_agent_composer"):
        payload = requirement_inputs(api, prefix, draft)
        st.session_state["agent_new_draft"] = payload
        if st.button("开始出题", type="primary", disabled=not ready, key=f"{prefix}_submit"):
            if not payload or (
                payload.get("adapt_existing") and not payload.get("existing_problem_id")
            ):
                st.error("请描述出题需求或选择至少一个条件；改编时需要选择已有题目。")
                return
            _post(api, "/agent/tasks", payload)
    st.caption("每次生成一道题。生成期间可以离开页面，稍后从出题记录继续。")


def _reuse(task: dict) -> None:
    st.session_state["agent_new_draft"] = deepcopy(task["request"])
    st.session_state["agent_composer_id"] = str(uuid4())
    update_route(agent_active_view="新建出题")


def record_list(api: ApiClient) -> None:
    columns = st.columns([3, 1, 1])
    for key in ("agent_history_search", "agent_history_status", "agent_history_difficulty"):
        restore_widget(key, "")
    columns[0].text_input(
        "搜索出题记录",
        key="agent_history_search",
        placeholder="搜索题目名称或最初的需求",
        on_change=save_widgets,
        args=("agent_history_search",),
        kwargs={"reset_page": "agent_history"},
    )
    status = columns[1].selectbox(
        "执行状态",
        ["", *STATUS],
        key="agent_history_status",
        format_func=lambda x: STATUS.get(x, "全部状态"),
        on_change=save_widgets,
        args=("agent_history_status",),
        kwargs={"reset_page": "agent_history"},
    )
    page, page_size = pagination_values("agent_history")
    params = {
        "page": page,
        "page_size": page_size,
        "search": st.session_state.agent_history_search,
        "status": status,
        "difficulty": st.session_state.agent_history_difficulty,
    }
    try:
        data = api.get("/agent/records", params=params)["data"]
    except Exception as exc:
        show_error(exc)
        st.button("重新加载记录")
        return
    difficulties = list(dict.fromkeys(["", *data["difficulties"], params["difficulty"]]))
    columns[2].selectbox(
        "难度",
        difficulties,
        key="agent_history_difficulty",
        format_func=lambda x: x or "全部难度",
        on_change=save_widgets,
        args=("agent_history_difficulty",),
        kwargs={"reset_page": "agent_history"},
    )
    list_count(data["total"])
    if not data["items"]:
        empty_state("没有符合条件的记录，调整筛选或开始一次新的出题。")
    else:
        labels, widths = ("题目 / 需求", "状态", "难度", "更新时间", "操作"), (3.5, 1.5, 1, 1.6, 2)
        with data_table(labels, widths, key="agent_history"):
            for item in data["items"]:
                rid = item["record_id"]
                with table_row(labels, widths, key=f"agent_{rid}") as row:
                    row[0].button(
                        item["title"],
                        key=f"agent_open_{rid}",
                        on_click=open_task,
                        args=(item["latest_task_id"],),
                    )
                    row[0].caption(f"{item['version_count']} 次版本 / 执行")
                    with row[1]:
                        badges(
                            [
                                (
                                    STATUS[item["status"]],
                                    "red"
                                    if item["status"] == "error"
                                    else "green"
                                    if item["status"] == "success"
                                    else "gray",
                                )
                            ]
                        )
                        if item["imported_problem_id"]:
                            st.caption(f"已导入 {item['imported_problem_id']}")
                        if item["status"] == "error" and item["usable_task_id"]:
                            st.caption("已有可用版本")
                    with row[2]:
                        cell_text(item["difficulty"] or "AI 决定")
                    row[3].caption(item["updated_at"].replace("T", " ")[:16] + " UTC")
                    with row[4]:
                        if item["editable_task_id"]:
                            st.button(
                                "修改",
                                key=f"agent_edit_{rid}",
                                on_click=open_task,
                                args=(item["editable_task_id"],),
                                kwargs={"edit": True},
                                disabled=bool(item["active_task_id"]),
                            )
                        if item["status"] in ("error", "cancelled"):
                            if st.button(
                                "重试",
                                key=f"agent_retry_{rid}",
                                disabled=bool(item["active_task_id"]),
                            ):
                                _post(api, f"/agent/tasks/{item['latest_task_id']}/retry")
                            st.button(
                                "修改要求后重试",
                                key=f"agent_retry_edit_{rid}",
                                on_click=open_task,
                                args=(item["latest_task_id"],),
                            )
                        elif not item["editable_task_id"]:
                            st.button(
                                "查看",
                                key=f"agent_view_{rid}",
                                on_click=open_task,
                                args=(item["latest_task_id"],),
                            )
    render_pagination("agent_history", total=data["total"])
    st.button("刷新记录", key="agent_refresh_history")
    if any(item["active_task_id"] for item in data["items"]):

        @st.fragment(run_every=5)
        def refresh_active_records() -> None:
            try:
                latest = api.get("/agent/records", params=params)["data"]
            except Exception:
                st.caption("自动刷新暂时不可用，可以点击“刷新记录”。")
                return
            if latest != data:
                st.rerun()

        refresh_active_records()


def preview(generated: dict) -> None:
    problem = generated["problem"]
    badges(
        [
            (str(problem.get("difficulty") or "未标注"), "orange"),
            (f"{len(problem.get('testcases', []))} 个测试点", "cyan"),
            *((str(t), "gray") for t in problem.get("tags", [])),
        ]
    )
    st.subheader(problem["title"])
    st.markdown(problem["description"])
    for label, key in [
        ("输入说明", "input_description"),
        ("输出说明", "output_description"),
        ("约束", "constraints"),
        ("提示", "hint"),
    ]:
        if problem.get(key):
            st.markdown(f"**{label}**")
            st.markdown(problem[key])
    for index, sample in enumerate(problem.get("samples", []), 1):
        st.markdown(f"**样例 {index}**")
        left, right = st.columns(2)
        left.code(sample["input"], language=None)
        right.code(sample["output"], language=None)
    st.caption(
        f"时间限制 {problem.get('time_limit', 2)} 秒 · "
        f"内存限制 {problem.get('memory_limit', 128)} MB"
    )
    with st.expander("参考解法与程序"):
        st.markdown(generated["solution_explanation"])
        st.markdown(generated["complexity_analysis"])
        st.code(generated["reference_solution"], language=generated["reference_solution_language"])
    with st.expander("测试数据"):
        for index, case in enumerate(problem.get("testcases", []), 1):
            st.caption(f"测试点 {index}")
            left, right = st.columns(2)
            left.code(case["input"], language=None)
            right.code(case["output"], language=None)


def editor(api: ApiClient, task: dict, busy: bool) -> None:
    candidate = deepcopy(task.get("final_problem") or task.get("draft"))
    if not candidate:
        empty_state("生成题目后即可编辑。")
        return
    prefix = f"agent_editor_{task['task_id']}"
    with st.form(prefix):
        problem = candidate["problem"]
        st.caption("保存会创建新版本；“验证并保存”只检查内容，不会让 AI 重写。")
        for label, name in [
            ("题目 ID", "id"),
            ("标题", "title"),
            ("来源", "source"),
            ("作者", "author"),
        ]:
            problem[name] = st.text_input(
                label, value=problem.get(name, ""), key=f"{prefix}_{name}"
            )
        for label, name in [
            ("题面", "description"),
            ("输入说明", "input_description"),
            ("输出说明", "output_description"),
            ("约束", "constraints"),
            ("提示", "hint"),
        ]:
            problem[name] = st.text_area(
                label, value=problem.get(name, ""), key=f"{prefix}_{name}", height=130
            )
        columns = st.columns(2)
        for col, name, options in (
            (columns[0], "difficulty", DIFFICULTY_LEVELS),
            (columns[1], "problem_type", PROBLEM_TYPES),
        ):
            current = problem.get(name, "")
            problem[name] = col.selectbox(
                LABELS[name],
                list(dict.fromkeys([current, *options])),
                key=f"{prefix}_{name}",
                accept_new_options=True,
            )
        tags = st.text_input("标签", "，".join(problem.get("tags", [])), key=f"{prefix}_tags")
        problem["tags"] = [x.strip() for x in tags.replace("，", ",").split(",") if x.strip()]
        limits = st.columns(2)
        problem["time_limit"] = limits[0].number_input(
            "时间限制（秒）",
            min_value=0.1,
            max_value=60.0,
            value=float(problem.get("time_limit", 2)),
            key=f"{prefix}_time",
        )
        problem["memory_limit"] = limits[1].number_input(
            "内存限制（MB）",
            min_value=16,
            max_value=4096,
            value=int(problem.get("memory_limit", 128)),
            key=f"{prefix}_memory",
        )
        for label, name in [("样例", "samples"), ("测试点", "testcases")]:
            st.markdown(f"**{label}**")
            problem[name] = st.data_editor(
                problem.get(name, []),
                num_rows="dynamic",
                key=f"{prefix}_{name}",
                column_config={
                    "input": st.column_config.TextColumn("输入", required=True),
                    "output": st.column_config.TextColumn("输出", required=True),
                },
                hide_index=True,
                width="stretch",
            )
        for label, name in [
            ("解法说明", "solution_explanation"),
            ("复杂度分析", "complexity_analysis"),
            ("参考程序", "reference_solution"),
        ]:
            candidate[name] = st.text_area(
                label,
                value=candidate[name],
                key=f"{prefix}_{name}",
                height=180 if name == "reference_solution" else 100,
            )
        languages = ["python", "cpp"]
        candidate["reference_solution_language"] = st.selectbox(
            "参考程序语言",
            languages,
            index=languages.index(candidate["reference_solution_language"]),
            key=f"{prefix}_language",
        )
        st.caption("错误解法用于检查测试点能否识别常见错误；可选，最多 5 个。")
        wrong = st.data_editor(
            [{"code": c} for c in candidate.get("wrong_solutions", [])] or [{"code": ""}],
            num_rows="dynamic",
            key=f"{prefix}_wrong",
            hide_index=True,
            column_config={"code": "错误解法代码"},
            width="stretch",
        )
        candidate["wrong_solutions"] = [v["code"] for v in wrong if v.get("code")]
        left, right = st.columns(2)
        saved = left.form_submit_button("保存新版本", disabled=busy)
        validated = right.form_submit_button("验证并保存", type="primary", disabled=busy)
    if saved or validated:
        _post(
            api,
            f"/agent/tasks/{task['task_id']}/versions",
            {"generated": candidate, "validate": validated},
        )


def _import_controls(api: ApiClient, task: dict, record: dict) -> None:
    if task.get("imported_problem_id"):
        st.success(f"此版本已导入为 {task['imported_problem_id']}。继续修改会创建新版本。")
        return
    if not task.get("final_problem") or task_status(task) != "success":
        return
    tid = task["task_id"]
    with st.expander("审阅并导入题目", expanded=True):
        target = record.get("imported_problem_id")
        choices = ["另存为新题", "更新原题"] if target else ["导入新题"]
        mode = st.radio("保存方式", choices, key=f"agent_import_mode_{tid}", horizontal=True)
        updating = mode == "更新原题"
        if updating:
            st.info(f"将更新题目 {target}，题目列表会展示更新后的内容。")
            problem_id = target
        else:
            original = task["final_problem"]["problem"]["id"]
            default_id = f"{original[:50]}_{tid[:8]}" if target else original
            problem_id = st.text_input("新题目 ID", default_id, key=f"agent_import_id_{tid}")
        confirmed = st.checkbox("我已审阅题面、参考解法和验证结果", key=f"agent_confirm_{tid}")
        if st.button(
            "确认更新原题" if updating else "确认导入",
            type="primary",
            disabled=not confirmed or bool(record["active_task_id"]),
            key=f"agent_import_{tid}",
        ):
            try:
                result = api.post(
                    f"/agent/tasks/{tid}/import",
                    json={
                        "confirm": True,
                        "update_existing": updating,
                        "problem_id": problem_id,
                    },
                )["data"]
            except Exception as exc:
                show_error(exc)
                if updating:
                    st.caption("如果原题已删除，请切换为“另存为新题”。")
            else:
                invalidate_problem_cache()
                st.session_state["agent_notice"] = f"已导入题目 {result['problem_id']}。"
                st.rerun()


def _conversation(api: ApiClient, task: dict, record: dict) -> None:
    with st.container(height=420, key="oj_agent_conversation"):
        with st.chat_message("user"):
            st.write(record["prompt"] or "按指定设置出题")
        for version in record["versions"]:
            if version["feedback"]:
                with st.chat_message("user"):
                    st.write(version["feedback"])
            with st.chat_message("assistant"):
                st.write(
                    f"版本 {version['revision']} · {OPERATIONS[version['operation']]} · "
                    f"{STATUS[task_status(version)]}"
                )
                if task_error(version):
                    st.caption(task_error(version))
    busy = bool(record["active_task_id"])
    tid = task["task_id"]
    st.caption(f"接下来的操作将基于版本 {task['revision']}。固定设置仍优先于修改意见。")
    with st.expander("查看或调整出题要求", expanded=task["status"] in ("error", "cancelled")):
        request = requirement_inputs(api, f"agent_requirements_{tid}", task["request"])
        st.session_state[f"agent_request_snapshot_{tid}"] = request
    if task["status"] in ("error", "cancelled"):
        left, right = st.columns(2)
        if left.button("重试", disabled=busy, key=f"agent_retry_detail_{tid}"):
            _post(api, f"/agent/tasks/{tid}/retry")
        if right.button("修改要求后重试", disabled=busy, key=f"agent_adjust_retry_{tid}"):
            _post(api, f"/agent/tasks/{tid}/retry", {"request": request})
        st.caption("重试使用当前模型配置，会新增执行记录并单独计费。")
    feedback = st.text_area(
        "继续修改",
        key=f"agent_feedback_{tid}",
        height=100,
        placeholder="例如：保留题目背景，增加一个边界样例。",
        disabled=busy,
    )
    if st.button(
        "发送修改要求",
        type="primary",
        key=f"agent_refine_{tid}",
        disabled=busy or not (task.get("draft") or task.get("final_problem")),
    ):
        if not feedback.strip():
            st.error("请填写修改意见。")
        else:
            _post(api, f"/agent/tasks/{tid}/refine", {"feedback": feedback, "request": request})


def _viewport(**kwargs):
    component = st.components.v2.component(
        "oj_agent_viewport",
        html='<span aria-hidden="true"></span>',
        css=":host {display:none}",
        js="""
        export default function({setStateValue}) {
            const query = window.matchMedia('(max-width: 1000px)');
            const update = () => setStateValue('compact', query.matches);
            update(); query.addEventListener('change', update);
            return () => query.removeEventListener('change', update);
        }
        """,
    )
    return component(**kwargs)


def task_monitor(api: ApiClient) -> None:
    tid = st.query_params.get("agent_task_id") or st.session_state.get("agent_task_id")
    if not tid:
        empty_state("从出题记录选择一个任务，或开始新的出题。")
        return
    try:
        task = api.get(f"/agent/tasks/{tid}")["data"]
        record = api.get(f"/agent/records/{task['record_id']}")["data"]
    except Exception as exc:
        show_error(exc)
        st.button("重新加载任务")
        return
    if notice := st.session_state.pop("agent_notice", None):
        st.success(notice)
    title, reuse = st.columns([3, 1])
    title.subheader(record["title"])
    reuse.button("沿用要求出新题", on_click=_reuse, args=(task,))
    versions = {v["task_id"]: v for v in record["versions"]}
    st.session_state.agent_version_selection = tid
    st.selectbox(
        "查看版本",
        list(versions),
        index=list(versions).index(tid),
        format_func=lambda x: (
            f"版本 {versions[x]['revision']} · "
            f"{OPERATIONS[versions[x]['operation']]} · {STATUS[task_status(versions[x])]}"
        ),
        key="agent_version_selection",
        on_change=_select_version,
    )
    active = record["active_task_id"]
    paused_key = f"agent_poll_paused_{active or tid}"
    if st.session_state.get(paused_key):
        st.warning("网络中断，自动刷新已暂停；后台任务仍可继续运行。")
        if st.button("恢复自动刷新", key="agent_resume_poll"):
            st.session_state[paused_key] = False
            st.rerun()

    @st.fragment(run_every=2 if active and not st.session_state.get(paused_key) else None)
    def progress() -> None:
        current = next((v for v in record['versions'] if v['task_id'] == active), task)
        if active and not st.session_state.get(paused_key):
            try:
                snapshot = api.get(f"/agent/records/{task['record_id']}")['data']
                current = next(v for v in snapshot['versions'] if v['task_id'] == active)
            except Exception:
                st.session_state[paused_key] = True
                st.rerun()
            if current["status"] not in ("pending", "running"):
                st.rerun()
        state = task_status(current)
        st.progress(
            current["progress"] / 100,
            text=f"{STAGES.get(current['stage'], current['stage'])} · {STATUS[state]}",
        )
        if active and st.button("停止任务", key=f"agent_stop_{active}"):
            try:
                api.post(f"/agent/tasks/{active}/cancel")
            except Exception as exc:
                show_error(exc)
            else:
                st.info("已请求停止。")

    progress()
    if task_error(task):
        st.error(task_error(task))
    if task["status"] in ("error", "cancelled") and record["usable_task_id"]:
        st.button("打开之前的可用版本", on_click=open_task, args=(record["usable_task_id"],))
    compact = bool(_viewport(key="agent_viewport", on_compact_change=lambda: None).compact)
    pane = (
        st.segmented_control("工作区", ["对话", "题目"], default="对话", key="agent_compact_pane")
        if compact
        else None
    )
    left, right = (None, None) if compact else st.columns([1, 1.7], gap="large")

    def content() -> None:
        generated = task.get("final_problem") or task.get("draft")
        restore_widget("agent_workspace_mode", "预览", options=["预览", "编辑"])
        mode = (
            st.segmented_control(
                "题目工作区",
                ["预览", "编辑"],
                key="agent_workspace_mode",
                on_change=save_widgets,
                args=("agent_workspace_mode",),
            )
            or "预览"
        )
        if mode == "编辑":
            editor(api, task, bool(active))
        elif generated:
            preview(generated)
        else:
            empty_state("题目生成后将显示在这里。你可以先查看左侧的需求和进度。")
        if task_status(task) == "draft" and st.button("验证此版本", disabled=bool(active)):
            _post(api, f"/agent/tasks/{tid}/validate")
        if task.get("validation_report"):
            with st.expander("验证结果"):
                report = task["validation_report"]
                if report["blocking_errors"]:
                    for error in report["blocking_errors"]:
                        st.error(error)
                else:
                    st.success("参考程序与样例、测试点检查通过。")
                for risk in report.get("unresolved_risks", []):
                    st.warning(risk)
                st.json(report, expanded=False)
        _import_controls(api, task, record)

    if compact:
        if pane == "题目":
            content()
        else:
            _conversation(api, task, record)
    else:
        with left:
            _conversation(api, task, record)
        with right:
            content()
    with st.expander("实际采用的要求、执行日志与费用"):
        st.json(task.get("effective_requirements") or task["request"], expanded=False)
        st.caption(
            f"本次执行 {task['total_tokens']} Token · {float(task['cost']):.2f} "
            f"{task['currency']}" + ("（估算）" if task["usage_estimated"] else "")
        )
        totals: dict[str, float] = {}
        for version in record["versions"]:
            totals[version["currency"]] = totals.get(version["currency"], 0) + float(
                version["cost"]
            )
        st.caption("此记录累计费用：" + " / ".join(f"{v:.2f} {k}" for k, v in totals.items()))
        if st.checkbox("加载执行日志", key=f"agent_show_events_{tid}"):
            try:
                events = api.get(f"/agent/tasks/{tid}/events", params={"after_id": 0})["data"]
                for event in events:
                    st.caption(f"{event['timestamp'][:19]} · {event['message']}")
            except Exception as exc:
                show_error(exc)
