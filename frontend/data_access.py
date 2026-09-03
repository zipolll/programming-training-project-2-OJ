"""Short-lived caches for low-sensitivity reference data."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient

REFERENCE_TTL_SECONDS = 15


@st.cache_data(ttl=REFERENCE_TTL_SECONDS, show_spinner=False)
def load_problem_summaries(
    base_url: str, _api: ApiClient
) -> list[dict[str, Any]]:
    """Cache only display metadata, never hidden testcase contents."""
    del base_url
    problems = _api.get("/problems/")["data"]
    allowed = ("id", "title", "difficulty", "tags", "source", "author")
    return [{key: problem.get(key) for key in allowed} for problem in problems]


@st.cache_data(ttl=REFERENCE_TTL_SECONDS, show_spinner=False)
def load_language_names(base_url: str, _api: ApiClient) -> list[str]:
    del base_url
    return list(_api.get("/languages/")["data"]["name"])


@st.cache_data(ttl=5, show_spinner=False)
def load_service_status(base_url: str, _api: ApiClient) -> str:
    del base_url
    return str(_api.get_health()["data"]["status"])


def load_submission_options(api: ApiClient) -> tuple[list[dict[str, Any]], list[str]]:
    """Reuse the same reference caches shared by browsing and authoring pages."""
    return (
        load_problem_summaries(api.base_url, api),
        load_language_names(api.base_url, api),
    )


def invalidate_problem_cache() -> None:
    load_problem_summaries.clear()
