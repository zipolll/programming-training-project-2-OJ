"""Reusable numbered pagination controls for Streamlit tables."""

import streamlit as st

from frontend.navigation import update_route

DEFAULT_PAGE_SIZE = 10


def page_count(total: int, page_size: int) -> int:
    """Return at least one display page, including for an empty result."""
    return max(1, (max(0, total) + page_size - 1) // page_size)


def page_window(page: int, pages: int, *, limit: int = 5) -> list[int]:
    """Return a compact, stable window of nearby page numbers."""
    pages = max(1, pages)
    page = min(max(1, page), pages)
    width = min(max(1, limit), pages)
    start = max(1, min(page - width // 2, pages - width + 1))
    return list(range(start, start + width))


def pagination_values(
    key: str,
    *,
    default_page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[int, int]:
    """Read the requested page without making or caching any API request."""
    page_key = f"{key}_page"
    try:
        page = max(1, int(st.query_params.get(page_key, 1)))
    except (ValueError, TypeError):
        page = 1
    # A locally clamped page never creates a history entry during rendering.
    override = st.session_state.get(f"{page_key}_clamped")
    if override and override[0] == page:
        page = override[1]
    st.session_state[page_key] = page
    return page, default_page_size


def reset_pagination(key: str) -> None:
    """Return a paginated view to its first page after filters change."""
    st.session_state[f"{key}_page"] = 1
    update_route(**{f"{key}_page": 1})


def _set_page(key: str, page: int) -> None:
    st.session_state[f"{key}_page"] = page
    st.session_state.pop(f"{key}_page_clamped", None)
    update_route(**{f"{key}_page": page})


def render_pagination(key: str, *, total: int, page_size: int = DEFAULT_PAGE_SIZE) -> None:
    """Render first, nearby pages, next, last and the current-page summary."""
    page, page_size = pagination_values(key, default_page_size=page_size)
    pages = page_count(total, page_size)
    if page > pages:
        st.session_state[f"{key}_page_clamped"] = (page, pages)
        st.rerun()

    numbers = page_window(page, pages)
    widths = [1.15, *([0.62] * len(numbers)), 0.62, 1.15, 1.65]
    with st.container(key=f"{key}_pagination"):
        columns = st.columns(widths)
        cursor = 0
        columns[cursor].button(
            "首页", key=f"{key}_first", disabled=page == 1,
            on_click=_set_page, args=(key, 1),
        )
        cursor += 1
        for number in numbers:
            columns[cursor].button(
                str(number), key=f"{key}_page_{number}",
                type="primary" if number == page else "secondary",
                on_click=_set_page, args=(key, number),
            )
            cursor += 1
        columns[cursor].button(
            ">", key=f"{key}_next", disabled=page >= pages, help="下一页",
            on_click=_set_page, args=(key, page + 1),
        )
        cursor += 1
        columns[cursor].button(
            "末页", key=f"{key}_last", disabled=page == pages,
            on_click=_set_page, args=(key, pages),
        )
        cursor += 1
        columns[cursor].markdown(
            f"<div class='oj-page-number'>第 {page} / {pages} 页</div>",
            unsafe_allow_html=True,
        )
