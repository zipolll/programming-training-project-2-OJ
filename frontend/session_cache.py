"""Short-lived per-browser-session cache for authenticated page data."""

from collections.abc import Callable, MutableMapping
from time import monotonic
from typing import Any, TypeVar

import streamlit as st

T = TypeVar("T")
SESSION_CACHE_KEY = "_oj_session_cache"


def cached_for_session(
    key: str,
    loader: Callable[[], T],
    *,
    ttl: float = 5.0,
    state: MutableMapping[str, Any] | None = None,
    now: float | None = None,
) -> T:
    """Cache private data only inside the current Streamlit browser session."""
    target = st.session_state if state is None else state
    cache = target.setdefault(SESSION_CACHE_KEY, {})
    current = monotonic() if now is None else now
    entry = cache.get(key)
    if isinstance(entry, tuple) and current - float(entry[0]) < ttl:
        return entry[1]
    value = loader()
    cache[key] = (current, value)
    return value


def clear_session_cache(
    prefix: str | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    """Invalidate either all private data or one logical cache namespace."""
    target = st.session_state if state is None else state
    if prefix is None:
        target.pop(SESSION_CACHE_KEY, None)
        return
    cache = target.get(SESSION_CACHE_KEY)
    if isinstance(cache, dict):
        for key in [item for item in cache if str(item).startswith(prefix)]:
            cache.pop(key, None)
