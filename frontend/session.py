"""Streamlit-session authentication state."""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from time import monotonic
from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.errors import ApiError

AUTH_USER_KEY = "auth_user"
API_CLIENT_KEY = "api_client"
_BROWSER_COOKIE_NAMES = ("_streamlit_session", "_streamlit_xsrf")
_CLIENT_TTL_SECONDS = 7 * 24 * 60 * 60
_MAX_CLIENTS = 256


@dataclass
class _ClientEntry:
    client: ApiClient
    last_seen: float


_CLIENT_REGISTRY: dict[str, _ClientEntry] = {}
_CLIENT_REGISTRY_LOCK = RLock()


def _browser_key(cookies: Mapping[str, str]) -> str | None:
    """Derive an opaque registry key without retaining a browser cookie value."""
    for name in _BROWSER_COOKIE_NAMES:
        value = cookies.get(name)
        if value:
            return sha256(f"{name}:{value}".encode()).hexdigest()
    return None


def _prune_clients(now: float) -> None:
    expired = [
        key
        for key, entry in _CLIENT_REGISTRY.items()
        if now - entry.last_seen > _CLIENT_TTL_SECONDS
    ]
    excess = max(0, len(_CLIENT_REGISTRY) - _MAX_CLIENTS + 1)
    oldest = sorted(
        (key for key in _CLIENT_REGISTRY if key not in expired),
        key=lambda key: _CLIENT_REGISTRY[key].last_seen,
    )[:excess]
    for key in [*expired, *oldest]:
        entry = _CLIENT_REGISTRY.pop(key, None)
        if entry is not None:
            entry.client.close()


def _forget_client(client: ApiClient) -> None:
    with _CLIENT_REGISTRY_LOCK:
        keys = [key for key, entry in _CLIENT_REGISTRY.items() if entry.client is client]
        for key in keys:
            _CLIENT_REGISTRY.pop(key, None)


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


def get_api_client(
    state: MutableMapping[str, Any] | None = None,
    browser_cookies: Mapping[str, str] | None = None,
) -> ApiClient:
    target = st.session_state if state is None else state
    cookies = st.context.cookies if browser_cookies is None else browser_cookies
    browser_key = _browser_key(cookies)
    existing = target.get(API_CLIENT_KEY)
    if isinstance(existing, ApiClient):
        if browser_key is not None:
            with _CLIENT_REGISTRY_LOCK:
                entry = _CLIENT_REGISTRY.get(browser_key)
                if entry is not None and entry.client is existing:
                    entry.last_seen = monotonic()
        return existing

    if browser_key is None:
        client = ApiClient(on_unauthorized=clear_auth)
    else:
        now = monotonic()
        with _CLIENT_REGISTRY_LOCK:
            _prune_clients(now)
            entry = _CLIENT_REGISTRY.get(browser_key)
            if entry is None:
                entry = _ClientEntry(ApiClient(on_unauthorized=clear_auth), now)
                _CLIENT_REGISTRY[browser_key] = entry
            else:
                entry.last_seen = now
            client = entry.client
    target[API_CLIENT_KEY] = client
    return client


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
    _forget_client(client)
    clear_auth(state)
