"""Shared card layouts retaining native Streamlit widgets and callbacks."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from html import escape
from typing import Any

import streamlit as st

from frontend.components.ui import page_header, section_header


@contextmanager
def page_heading(title: str, subtitle: str, *, key: str) -> Iterator[None]:
    """Keep the heading and its native action controls in a single layout group."""
    with st.container(key=f"oj_page_heading_{key}"):
        heading, actions = st.columns([3, 2], vertical_alignment="center")
        with heading:
            page_header(title, subtitle)
        with actions, st.container(horizontal=True, horizontal_alignment="right"):
            yield


@contextmanager
def form_row(key: str, widths: Sequence[float] = (1, 1)) -> Iterator[list[Any]]:
    """Pair short fields without introducing another form or changing callbacks."""
    with st.container(key=f"oj_form_row_{key}"):
        yield st.columns(widths, gap="medium")


@contextmanager
def split_view(key: str, widths: Sequence[float] = (2, 1)) -> Iterator[list[Any]]:
    """A native column group that stacks at the workspace's wide breakpoint."""
    with st.container(key=f"oj_split_{key}"):
        yield st.columns(widths, gap="large")


@contextmanager
def section_card(
    title: str, *, key: str, icon: str = "✦", tone: str = "default", stretch: bool = False
) -> Iterator[None]:
    """Group widgets without creating a form or changing their state lifecycle."""
    with st.container(key=f"oj_panel_{tone}_{key}", height="stretch" if stretch else "content"):
        if title:
            with st.container(key=f"oj_panel_heading_{key}"):
                section_header(title, icon=icon)
        with st.container(key=f"oj_panel_body_{key}"):
            yield


@contextmanager
def data_table(
    labels: Sequence[str], widths: Sequence[float], *, key: str
) -> Iterator[None]:
    """One table shell; its responsive rows reuse the same native widgets."""
    with st.container(key=f"oj_table_{key}"):
        with st.container(key=f"oj_table_header_{key}"):
            columns = st.columns(widths, vertical_alignment="center")
            for column, label in zip(columns, labels, strict=True):
                with column:
                    cell_text(label, emphasis=True)
        yield


@contextmanager
def table_row(
    labels: Sequence[str], widths: Sequence[float], *, key: str
) -> Iterator[list[Any]]:
    """Keep each record together, including optional expanded details."""
    with st.container(key=f"oj_record_{key}"):
        columns = st.columns(widths, vertical_alignment="center")
        for column, label in zip(columns, labels, strict=True):
            column.markdown(
                f'<span class="oj-field-label">{escape(label)}</span>',
                unsafe_allow_html=True,
            )
        yield columns


def cell_text(value: Any, *, emphasis: bool = False, tone: str = "default") -> None:
    """Render escaped text, without Markdown's paragraph margin or code coercion."""
    modifier = " oj-cell-text--strong" if emphasis else ""
    st.markdown(
        f'<div class="oj-cell-text oj-cell-text--{escape(tone, quote=True)}{modifier}">'
        f'{escape(str(value if value is not None else "—"))}</div>',
        unsafe_allow_html=True,
    )
