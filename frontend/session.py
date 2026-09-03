"""Authentication state and secure browser refresh recovery."""

from collections.abc import MutableMapping
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.auth_bridge import mount_auth_bridge
from frontend.errors import ApiError

AUTH_USER_KEY = "auth_user"
API_CLIENT_KEY = "api_client"
BRIDGE_ACTION_KEY = "auth_bridge_action"
BRIDGE_NONCE_KEY = "auth_bridge_nonce"
BRIDGE_TOKEN_KEY = "auth_bridge_claim"
BRIDGE_TICKET_KEY = "auth_bridge_last_ticket"
BRIDGE_ATTEMPTED_KEY = "auth_bridge_attempted"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _state(state: MutableMapping[str, Any] | None) -> MutableMapping[str, Any]:
    return st.session_state if state is None else state


def clear_auth(state: MutableMapping[str, Any] | None = None) -> None:
    _state(state)[AUTH_USER_KEY] = None


def set_auth_user(
    user: dict[str, Any], state: MutableMapping[str, Any] | None = None
) -> None:
    _state(state)[AUTH_USER_KEY] = dict(user)


def current_user(state: MutableMapping[str, Any] | None = None) -> dict[str, Any] | None:
    value = _state(state).get(AUTH_USER_KEY)
    return dict(value) if isinstance(value, dict) else None


def _set_bridge_action(
    action: str,
    state: MutableMapping[str, Any] | None = None,
    *,
    token: str | None = None,
) -> None:
    target = _state(state)
    target[BRIDGE_ACTION_KEY] = action
    target[BRIDGE_NONCE_KEY] = token_urlsafe(12)
    target[BRIDGE_ATTEMPTED_KEY] = False
    if token is None:
        target.pop(BRIDGE_TOKEN_KEY, None)
    else:
        target[BRIDGE_TOKEN_KEY] = token


def request_browser_bridge_clear(
    state: MutableMapping[str, Any] | None = None,
) -> None:
    _set_bridge_action("clear", state)


def browser_bridge_base_url(api_base_url: str, browser_host: str | None = None) -> str:
    """Keep local browser fetches on the same hostname for strict cookies."""
    if browser_host is None:
        try:
            browser_host = st.context.headers.get("Host")
        except RuntimeError:
            browser_host = None
    if not browser_host:
        return api_base_url
    browser_parts = urlsplit(f"//{browser_host}")
    api_parts = urlsplit(api_base_url)
    browser_name = browser_parts.hostname
    api_name = api_parts.hostname
    if browser_name not in _LOOPBACK_HOSTS or api_name not in _LOOPBACK_HOSTS:
        return api_base_url
    formatted_host = f"[{browser_name}]" if ":" in browser_name else browser_name
    netloc = formatted_host
    if api_parts.port is not None:
        netloc = f"{netloc}:{api_parts.port}"
    return urlunsplit(
        (api_parts.scheme, netloc, api_parts.path, api_parts.query, api_parts.fragment)
    )


def get_api_client(state: MutableMapping[str, Any] | None = None) -> ApiClient:
    target = _state(state)
    existing = target.get(API_CLIENT_KEY)
    if isinstance(existing, ApiClient):
        return existing

    def unauthorized() -> None:
        clear_auth(target)
        request_browser_bridge_clear(target)

    client = ApiClient(on_unauthorized=unauthorized)
    target[API_CLIENT_KEY] = client
    return client


def prepare_browser_bridge(
    api: ApiClient,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    """Issue a one-use claim after a successful password login."""
    envelope = api.post("/auth/bridge/issue")
    token = envelope.get("data", {}).get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Authentication recovery token was not issued")
    _set_bridge_action("claim", state, token=token)


def sync_browser_auth(
    api: ApiClient,
    state: MutableMapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Process browser bridge results before role-aware navigation is built."""
    target = _state(state)
    pending_action = target.get(BRIDGE_ACTION_KEY)
    if pending_action in (None, "idle"):
        if api.has_cookies or target.get(BRIDGE_ATTEMPTED_KEY):
            return current_user(target)
        action = "restore"
    else:
        action = str(pending_action)
    nonce = target.get(BRIDGE_NONCE_KEY)
    if not isinstance(nonce, str):
        nonce = token_urlsafe(12)
        target[BRIDGE_NONCE_KEY] = nonce
    token = target.get(BRIDGE_TOKEN_KEY)
    result = mount_auth_bridge(
        base_url=browser_bridge_base_url(api.base_url),
        action=action,
        nonce=nonce,
        token=token if isinstance(token, str) else None,
    )

    status = getattr(result, "status", None)
    if isinstance(status, str) and status.endswith(f":{nonce}"):
        target[BRIDGE_ACTION_KEY] = "idle"
        target[BRIDGE_ATTEMPTED_KEY] = True
        target.pop(BRIDGE_TOKEN_KEY, None)

    ticket = getattr(result, "ticket", None)
    ticket_nonce = getattr(result, "ticket_nonce", None)
    if not isinstance(ticket, str) or ticket_nonce != nonce:
        return current_user(target)
    ticket_fingerprint = sha256(ticket.encode()).hexdigest()
    if target.get(BRIDGE_TICKET_KEY) == ticket_fingerprint:
        return current_user(target)
    target[BRIDGE_TICKET_KEY] = ticket_fingerprint
    try:
        api.post("/auth/bridge/exchange", json={"ticket": ticket})
        user = restore_identity(api, target)
    except ApiError:
        request_browser_bridge_clear(target)
        return None
    target[BRIDGE_ACTION_KEY] = "idle"
    target[BRIDGE_ATTEMPTED_KEY] = True
    return user


def restore_identity(
    api: ApiClient | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    client = api or get_api_client(state)
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
    client = api or get_api_client(state)
    client.clear_cookies()
    clear_auth(state)
    request_browser_bridge_clear(state)
