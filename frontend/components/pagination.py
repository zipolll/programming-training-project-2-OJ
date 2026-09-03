"""Compact, reusable pagination controls for Streamlit tables."""

from collections.abc import Sequence

import streamlit as st

DEFAULT_PAGE_SIZES = (10, 20, 50)


def page_count(total: int, page_size: int) -> int:
    """Return at least one display page, including for an empty result."""
    return max(1, (max(0, total) + page_size - 1) // page_size)


def pagination_values(
    key: str,
    *,
    default_page_size: int = 10,
) -> tuple[int, int]:
    """Read the requested page without making or caching any API request."""
    page_key = f"{key}_page"
    size_key = f"{key}_page_size"
    st.session_state.setdefault(page_key, 1)
    st.session_state.setdefault(size_key, default_page_size)
    return max(1, int(st.session_state[page_key])), int(st.session_state[size_key])


def reset_pagination(key: str) -> None:
    """Return a paginated view to its first page after filters change."""
    st.session_state[f"{key}_page"] = 1


def render_pagination(
    key: str,
    *,
    total: int,
    page_sizes: Sequence[int] = DEFAULT_PAGE_SIZES,
) -> None:
    """Render one aligned row and rerun only when the requested page changes."""
    page, page_size = pagination_values(key, default_page_size=int(page_sizes[0]))
    pages = page_count(total, page_size)
    if page > pages:
        st.session_state[f"{key}_page"] = pages
        st.rerun()

    def page_size_changed() -> None:
        reset_pagination(key)

    with st.container(key=f"{key}_pagination"):
        size_col, previous_col, number_col, next_col = st.columns([1.2, 1, 1.05, 1])
        size_col.selectbox(
            "每页数量",
            list(page_sizes),
            key=f"{key}_page_size",
            format_func=lambda value: f"{value} 条/页",
            label_visibility="collapsed",
            on_change=page_size_changed,
        )
        if previous_col.button(
            "上一页",
            key=f"{key}_previous",
            disabled=page <= 1,
            use_container_width=True,
        ):
            st.session_state[f"{key}_page"] = page - 1
            st.rerun()
        number_col.markdown(
            f"<div class='oj-page-number'>第 {page} / {pages} 页</div>",
            unsafe_allow_html=True,
        )
        if next_col.button(
            "下一页",
            key=f"{key}_next",
            disabled=page >= pages,
            use_container_width=True,
        ):
            st.session_state[f"{key}_page"] = page + 1
            st.rerun()
