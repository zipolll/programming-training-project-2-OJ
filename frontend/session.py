"""Authentication state and secure browser refresh recovery."""

from collections.abc import MutableMapping
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any

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
    if token is None:
        target.pop(BRIDGE_TOKEN_KEY, None)
    else:
        target[BRIDGE_TOKEN_KEY] = token


def request_browser_bridge_clear(
    state: MutableMapping[str, Any] | None = None,
) -> None:
    _set_bridge_action("clear", state)


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
    action = str(target.get(BRIDGE_ACTION_KEY) or ("idle" if api.has_cookies else "restore"))
    nonce = target.get(BRIDGE_NONCE_KEY)
    if not isinstance(nonce, str):
        nonce = token_urlsafe(12)
        target[BRIDGE_NONCE_KEY] = nonce
    token = target.get(BRIDGE_TOKEN_KEY)
    result = mount_auth_bridge(
        base_url=api.base_url,
        action=action,
        nonce=nonce,
        token=token if isinstance(token, str) else None,
    )

    status = getattr(result, "status", None)
    if isinstance(status, str) and status.endswith(f":{nonce}"):
        target[BRIDGE_ACTION_KEY] = "idle"
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
