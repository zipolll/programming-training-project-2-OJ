"""Atomic URL navigation and URL-backed widgets; no history writes on rendering."""

from urllib.parse import urlencode

import streamlit as st


def update_route(**changes) -> None:
    params = st.query_params.to_dict()
    for key, value in changes.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = str(value)
    if params != st.query_params.to_dict():
        st.query_params.from_dict(params)


def restore_widget(key: str, default="", *, options=None):
    """Hydrate before widget creation on every run, including popstate reruns."""
    value = st.query_params.get(key, default)
    if options is not None and value not in options:
        value = default
    if key not in st.session_state or st.session_state[key] != value:
        st.session_state[key] = value
    return value


def save_widgets(*keys: str, reset_page: str | None = None) -> None:
    changes = {key: st.session_state.get(key, "") for key in keys}
    if reset_page:
        changes[f"{reset_page}_page"] = 1
    update_route(**changes)


def open_submission(submission_id: str) -> None:
    params = st.query_params.to_dict()
    params["submission"] = str(submission_id)
    page = st.session_state.get("oj_submission_page")
    if page is not None:
        navigate_page(page, params, rerun=False)
    else:
        update_route(submission=submission_id)


def navigate_page(page, params: dict, *, rerun: bool = True) -> None:
    """One native document navigation; avoid switch_page's intermediate query URL."""
    base = str(st.get_option("server.baseUrlPath") or "").strip("/")
    path = "/" + "/".join(part for part in (base, page.url_path) if part)
    st.session_state["oj_pending_navigation"] = path + ("?" + urlencode(params) if params else "")
    if rerun:
        st.rerun()


def mount_navigation() -> None:
    target = st.session_state.pop("oj_pending_navigation", None)
    redirect = st.components.v2.component(
        "oj_page_navigation", html="<span></span>", css=":host {display:none}",
        js="""export default function({data}) {
          // Streamlit 1.63 can send stale query state on a same-page popstate.
          // Reload the actual address without adding a history entry. Tab-local
          // code drafts and the existing login bridge survive this navigation.
          const restoreAddress = () => window.location.reload();
          window.addEventListener('popstate', restoreAddress);
          if (data.target) {
            const url = new URL(data.target, window.location.origin);
            if (url.origin === window.location.origin) window.location.assign(url.href);
          }
          return () => window.removeEventListener('popstate', restoreAddress);
        }""",
    )
    redirect(data={"target": target}, key="oj_redirect")
    if target:
        st.stop()
