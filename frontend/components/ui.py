"""Safe reusable visual components for Streamlit pages."""

from html import escape
from textwrap import dedent
from typing import Any

import streamlit as st


def _safe(value: Any) -> str:
    return escape(str(value), quote=True)


def _html(value: str) -> str:
    """Remove Markdown-significant indentation from an HTML fragment."""
    return dedent(value).strip()


def page_header(
    title: str,
    subtitle: str,
    *,
    icon: str = "🏆",
    eyebrow: str = "PROGRAMMING TRAINING OJ",
    variant: str = "default",
) -> None:
    modifier = " oj-hero--ai" if variant == "ai" else ""
    st.markdown(
        _html(
            f"""
            <section class="oj-hero{modifier}">
              <div class="oj-hero__eyebrow">{_safe(eyebrow)}</div>
              <h1><span class="oj-hero__icon">{_safe(icon)}</span>{_safe(title)}</h1>
              <p>{_safe(subtitle)}</p>
            </section>
            """
        ),
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str = "", *, icon: str = "✦") -> None:
    description = f"<p>{_safe(subtitle)}</p>" if subtitle else ""
    st.markdown(
        _html(
            f"""
            <div class="oj-section-title">
              <span class="oj-section-title__icon">{_safe(icon)}</span>
              <div><h2>{_safe(title)}</h2>{description}</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def badges(items: list[tuple[str, str]]) -> None:
    content = "".join(
        f'<span class="oj-badge oj-badge--{_safe(tone)}">{_safe(text)}</span>'
        for text, tone in items
    )
    st.markdown(f'<div class="oj-badges">{content}</div>', unsafe_allow_html=True)


def list_count(total: int) -> None:
    """One consistent total badge for every list; page position lives in pagination."""
    badges([(f"共 {total} 条", "cyan")])


def info_card(
    label: str, value: Any, *, icon: str = "", compact: bool = False
) -> None:
    modifier = " oj-info-card--compact" if compact else ""
    st.markdown(
        _html(
            f"""
            <div class="oj-info-card{modifier}">
              <div class="oj-info-card__label">{_safe(icon)} {_safe(label)}</div>
              <div class="oj-info-card__value">{_safe(value)}</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def feature_grid(items: list[tuple[str, str, str]]) -> None:
    cards = "".join(
        _html(
            f"""
            <article class="oj-feature-card">
              <span class="oj-feature-card__icon">{_safe(icon)}</span>
              <h3>{_safe(title)}</h3><p>{_safe(description)}</p>
            </article>
            """
        )
        for icon, title, description in items
    )
    st.markdown(f'<div class="oj-feature-grid">{cards}</div>', unsafe_allow_html=True)


def empty_state(message: str, *, icon: str = "📭") -> None:
    st.markdown(
        '<div class="oj-empty">'
        f'<span class="oj-empty__icon">{_safe(icon)}</span>{_safe(message)}'
        "</div>",
        unsafe_allow_html=True,
    )


def timeline_event(timestamp: Any, stage: Any, message: Any) -> None:
    st.markdown(
        _html(
            f"""
            <div class="oj-timeline">
              <div class="oj-timeline__meta">{_safe(timestamp)} · {_safe(stage)}</div>
              <div class="oj-timeline__message">{_safe(message)}</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def status_tone(status: str) -> str:
    normalized = status.lower()
    tone = {
        "success": "green",
        "ac": "green",
        "pending": "orange oj-badge--pending",
        "running": "cyan oj-badge--pending",
        "error": "red",
        "cancelled": "red",
        "wa": "red",
        "ce": "blue",
        "re": "orange",
        "tle": "yellow",
        "mle": "yellow",
        "unk": "gray",
    }.get(normalized, "gray")
    return tone


def status_badge(status: str) -> None:
    from frontend.models import status_text

    badges([(status_text(status), status_tone(status))])
