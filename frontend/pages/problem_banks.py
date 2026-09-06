"""Separate collection browsing, authoring and problem selection pages."""

import streamlit as st

from frontend.components.common import show_error
from frontend.components.layout import section_card
from frontend.components.ui import badges, empty_state, list_count, page_header
from frontend.navigation import navigate_page, update_route
from frontend.pages.problems import (
    _requested_problem_id,
    render_problem_catalogue,
    render_problem_detail,
)


def open_bank(bank_id: int | None, view: str = "") -> None:
    for name in list(st.session_state):
        if name.startswith("bank_selection_"):
            del st.session_state[name]
    update_route(bank=bank_id, bank_view=view, problem=None, action=None)


def start_creation() -> None:
    st.session_state.pop("bank_draft_new", None)
    open_bank(None, "create")


def draft_key(bank: dict | None) -> str:
    return f"bank_draft_{bank['id']}" if bank else "bank_draft_new"


def get_draft(bank: dict | None) -> dict:
    return st.session_state.setdefault(
        draft_key(bank),
        {
            "name": (bank or {}).get("name", ""),
            "description": (bank or {}).get("description", ""),
            "problem_ids": [],
        },
    )


def render_metadata(bank: dict | None) -> dict:
    draft = get_draft(bank)
    key = draft_key(bank)

    def remember(field: str) -> None:
        draft[field] = st.session_state[f"{key}_widget_{field}"]

    with section_card("题库信息", key=f"{key}_metadata", icon="✏️"):
        st.text_input(
            "题库名称",
            value=draft["name"],
            max_chars=40,
            key=f"{key}_widget_name",
            on_change=remember,
            args=("name",),
        )
        st.text_area(
            "题库描述",
            value=draft["description"],
            max_chars=200,
            height=150,
            key=f"{key}_widget_description",
            on_change=remember,
            args=("description",),
        )
    return draft


def render_add_problems(api, bank: dict | None) -> None:
    bank_id = bank["id"] if bank else None
    return_view = "edit" if bank else "create"
    st.button(
        "← 返回编辑题库" if bank else "← 返回创建题库",
        on_click=open_bank,
        args=(bank_id, return_view),
    )
    page_header("增加题目", "筛选并勾选要收录的题目，确认后返回题库编辑页面。", icon="➕")
    draft = get_draft(bank)
    existing = {p["id"] for p in bank["problems"]} if bank else set(draft["problem_ids"])
    try:
        available = api.get("/problems/")["data"]
        problems = [p for p in available if p["id"] not in existing]
    except Exception as exc:
        show_error(exc)
        return
    key = f"bank_add_{bank_id or 'new'}"
    selected = render_problem_catalogue(
        api, problems, key=key, selectable=True, show_count=False,
        empty_message=(
            "当前题目均已收录到此题库，无需重复添加。" if available
            else "暂无可选题目，请先在命题中心创建题目。"
        ),
    )
    if st.button("确认增加", type="primary", disabled=not selected, key="bank_confirm_add"):
        try:
            if bank:
                api.post(f"/problem-banks/{bank_id}/problems", json={"problem_ids": selected})
            else:
                draft["problem_ids"] = list(dict.fromkeys([*draft["problem_ids"], *selected]))
        except Exception as exc:
            show_error(exc)
        else:
            open_bank(bank_id, return_view)
            st.session_state["bank_notice"] = (
                "题目已增加。" if bank else "题目已选入，保存题库后生效。"
            )
            st.rerun()


def render_editor(api, bank: dict | None) -> None:
    bank_id = bank["id"] if bank else None
    st.button("← 返回题库主页" if bank else "← 返回我的题库", on_click=open_bank, args=(bank_id,))
    page_header("编辑题库" if bank else "创建题库", "填写题库信息，整理练习题目。", icon="✏️")
    draft = render_metadata(bank)
    if bank:
        problems = bank["problems"]
    else:
        try:
            available = {p["id"]: p for p in api.get("/problems/")["data"]}
        except Exception as exc:
            show_error(exc)
            return
        problems = [
            available.get(pid, {"id": pid, "title": "题目已删除", "available": False})
            for pid in sorted(draft["problem_ids"])
        ]
    key = f"bank_edit_{bank_id or 'new'}"

    def remove_problem(pid: str) -> None:
        try:
            if bank:
                api.post(f"/problem-banks/{bank_id}/problems/remove", json={"problem_ids": [pid]})
            else:
                draft["problem_ids"] = [item for item in draft["problem_ids"] if item != pid]
        except Exception as exc:
            show_error(exc)
            return
        st.session_state["bank_notice"] = "题目已移出，原题不受影响。"
        st.rerun()

    with section_card("题目", key=f"{key}_problems", icon="📚"):
        if st.button("增加题目", icon=":material/add:", key="bank_add_problems"):
            open_bank(bank_id, "add")
            st.rerun()
        render_problem_catalogue(api, problems, key=key, on_remove=remove_problem, show_count=False)
    st.divider()
    if st.button("保存名称与描述" if bank else "保存题库", type="primary", key="bank_save"):
        if not draft["name"].strip():
            st.error("请输入题库名称。")
            return
        payload = {"name": draft["name"].strip(), "description": draft["description"].strip()}
        try:
            if bank:
                api.put(f"/problem-banks/{bank_id}", json=payload)
            else:
                result = api.post(
                    "/problem-banks/",
                    json={
                        **payload,
                        "problem_ids": draft["problem_ids"],
                    },
                )["data"]
                bank_id = result["id"]
        except Exception as exc:
            show_error(exc)
        else:
            st.session_state.pop(draft_key(bank), None)
            open_bank(bank_id)
            st.session_state["bank_notice"] = "题库已保存。"
            st.rerun()


def render_delete(api, bank: dict) -> None:
    st.button("← 返回题库主页", on_click=open_bank, args=(bank["id"],))
    page_header("删除题库", bank["name"], icon="🗑️")
    st.warning("删除题库将移除所有收录关系，原题不受影响。")
    confirmed = st.checkbox("确认删除此题库", key=f"bank_delete_confirm_{bank['id']}")
    if st.button("确认删除", disabled=not confirmed, type="primary", key="bank_confirm_delete"):
        try:
            api.delete(f"/problem-banks/{bank['id']}")
        except Exception as exc:
            show_error(exc)
        else:
            st.session_state.pop(draft_key(bank), None)
            open_bank(None)
            st.session_state["bank_notice"] = "题库已删除。"
            st.rerun()


def render_problem_banks(api, user: dict) -> None:
    notice = st.session_state.pop("bank_notice", None)
    if notice:
        st.success(notice)
    raw_id = st.query_params.get("bank")
    view = st.query_params.get("bank_view", "")
    if view not in {"", "add", "create", "edit", "delete"}:
        view = ""
    bank = None
    if raw_id:
        try:
            bank = api.get(f"/problem-banks/{int(raw_id)}")["data"]
        except Exception as exc:
            st.button("← 返回我的题库", on_click=open_bank, args=(None,))
            show_error(exc)
            return
    problem_id = _requested_problem_id()
    return_problem = st.query_params.get("return_problem")
    if return_problem and st.button("← 返回原题目", key="bank_return_problem"):
        params = st.query_params.to_dict()
        params.update(problem=return_problem)
        for name in ("bank", "bank_view", "return_problem", "action"):
            params.pop(name, None)
        navigate_page(st.session_state["oj_problems_page"], params)
    if problem_id and (bank or view in {"create", "add"}):
        label = {"add": "← 返回增加题目", "edit": "← 返回编辑题库", "create": "← 返回创建题库"}
        render_problem_detail(api, problem_id, user, back_label=label.get(view, "← 返回当前题库"))
        return
    if view == "add":
        render_add_problems(api, bank)
        return
    if view == "create" and not bank or view == "edit" and bank:
        render_editor(api, bank)
        return
    if view == "delete" and bank:
        render_delete(api, bank)
        return
    if bank:
        st.button("← 返回我的题库", on_click=open_bank, args=(None,))
        page_header(bank["name"], "按自己的学习安排练习题目。", icon="📚")
        with section_card("题库描述", key=f"bank_description_{bank['id']}", icon="📖"):
            st.text(bank["description"] or "还没有题库简介")
        render_problem_catalogue(api, bank["problems"], key=f"bank_{bank['id']}")
        st.divider()
        with st.container(horizontal=True):
            st.button("编辑题库", on_click=open_bank, args=(bank["id"], "edit"), key="bank_edit")
            st.button(
                "删除题库", on_click=open_bank, args=(bank["id"], "delete"), key="bank_delete"
            )
        return
    page_header("我的题库", "点击题库名称，开始练习。", icon="📚")
    try:
        banks = api.get("/problem-banks/")["data"]
    except Exception as exc:
        show_error(exc)
        return
    list_count(len(banks))
    if not banks:
        empty_state("你还没有题库，点击下方创建题库。", icon="📚")
    for item in banks:
        with st.container(key=f"bank_link_card_{item['id']}"):
            st.button(
                item["name"],
                type="tertiary",
                key=f"bank_open_{item['id']}",
                on_click=open_bank,
                args=(item["id"],),
            )
            st.caption(item["description"] or "还没有题库简介")
            badges([(f"📚 已收录 {item['problem_count']} 道题", "blue")])
            if not item["problem_count"]:
                st.caption("尚未收录题目，添加题目开始练习。")
    st.button("创建题库", icon=":material/add:", on_click=start_creation, key="bank_create")
