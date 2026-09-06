"""Owned-bank membership controls without moving or deleting original problems."""

import streamlit as st

from frontend.components.common import show_error
from frontend.navigation import navigate_page


def clear_selection(key: str) -> None:
    for name in list(st.session_state):
        if name.startswith(f"bank_selection_{key}_"):
            del st.session_state[name]


def prepare_selection(key: str, context: tuple, visible: list[dict]) -> str:
    prefix = f"bank_selection_{key}"
    signature = (*context, tuple(p["id"] for p in visible))
    if st.session_state.get(f"{prefix}_context") != signature:
        clear_selection(key)
        st.session_state[f"{prefix}_context"] = signature
    return prefix


def render_add_to_bank(api, problem_id: str) -> None:
    with st.popover("添加到题库", icon=":material/library_add:"):
        try:
            banks = api.get("/problem-banks/")["data"]
        except Exception as exc:
            show_error(exc)
            return
        if not banks:
            st.info("还没有题库，先创建一个吧。")
            if st.button("创建题库", key=f"detail_create_bank_{problem_id}"):
                params = st.query_params.to_dict()
                params.update(bank_view="create", return_problem=problem_id)
                params.pop("problem", None)
                params.pop("bank", None)
                navigate_page(st.session_state["oj_bank_page"], params)
            return
        options = {item["id"]: item["name"] for item in banks}
        target = st.selectbox("选择题库", list(options), format_func=options.get,
                             key=f"detail_bank_target_{problem_id}")
        if st.button("确认添加", key=f"detail_bank_add_{problem_id}", type="primary"):
            try:
                api.post(f"/problem-banks/{target}/problems", json={"problem_ids": [problem_id]})
            except Exception as exc:
                show_error(exc)
            else:
                st.success("已收录到题库；重复添加不会产生重复记录。")
