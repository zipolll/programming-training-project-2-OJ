"""Streamlit-session authentication state."""

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.errors import ApiError

AUTH_USER_KEY = "auth_user"
API_CLIENT_KEY = "api_client"


def clear_auth(state: MutableMapping[str, Any] | None = None) -> None:
    target = st.session_state if state is None else state
    target[AUTH_USER_KEY] = None


def set_auth_user(user: dict[str, Any], state: MutableMapping[str, Any] | None = None) -> None:
    target = st.session_state if state is None else state
    target[AUTH_USER_KEY] = dict(user)


def current_user(state: MutableMapping[str, Any] | None = None) -> dict[str, Any] | None:
    target = st.session_state if state is None else state
    value = target.get(AUTH_USER_KEY)
    return dict(value) if isinstance(value, dict) else None


def get_api_client() -> ApiClient:
    if API_CLIENT_KEY not in st.session_state:
        st.session_state[API_CLIENT_KEY] = ApiClient(on_unauthorized=clear_auth)
    return st.session_state[API_CLIENT_KEY]


def restore_identity(
    api: ApiClient | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    client = api or get_api_client()
    if not client.has_cookies:
        clear_auth(state)
        return None
    try:
        envelope = client.get("/users/me")
    except ApiError as exc:
        if exc.status_code == 403 and "banned" in exc.message.lower():
            logout_local(client, state)
        raise
    set_auth_user(envelope["data"], state)
    return envelope["data"]


def logout_local(
    api: ApiClient | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    client = api or get_api_client()
    client.clear_cookies()
    clear_auth(state)
