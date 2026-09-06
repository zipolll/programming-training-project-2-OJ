"""Invisible browser bridge for HttpOnly authentication recovery."""

from typing import Any

import streamlit as st

_BRIDGE_JS = r"""
export default function(component) {
    const {data, setStateValue} = component;
    const nonce = String(data.nonce || "");
    if (!nonce) return;

    const headers = {"Content-Type": "application/json", "X-OJ-Bridge": "1"};
    const endpoint = `${String(data.baseUrl).replace(/\/$/, "")}/auth/bridge`;
    const options = {method: "POST", credentials: "include", headers};

    async function run() {
        try {
            if (data.action === "claim") {
                options.body = JSON.stringify({token: data.token});
                const response = await fetch(`${endpoint}/claim`, options);
                setStateValue("status", `${response.ok ? "claimed" : "failed"}:${nonce}`);
            } else if (data.action === "clear") {
                try {
                    const owner = sessionStorage.getItem("oj-code-user");
                    for (const key of Object.keys(sessionStorage)) {
                        if (owner && key.startsWith(`oj-code:${owner}:`)) {
                            sessionStorage.removeItem(key);
                        }
                    }
                    sessionStorage.removeItem("oj-code-user");
                } catch (_) { /* Storage access must not prevent server logout. */ }
                await fetch(`${endpoint}/clear`, options);
                setStateValue("status", `cleared:${nonce}`);
            } else if (data.action === "restore") {
                const response = await fetch(`${endpoint}/ticket`, options);
                if (!response.ok) {
                    setStateValue("status", `anonymous:${nonce}`);
                    return;
                }
                const payload = await response.json();
                const ticket = payload && payload.data && payload.data.ticket;
                if (typeof ticket === "string") {
                    setStateValue("ticket_result", {ticket, nonce});
                }
            }
        } catch (_) {
            setStateValue("status", `unavailable:${nonce}`);
        }
    }
    run();
}
"""

_bridge_component = st.components.v2.component(
    "oj_auth_bridge",
    html="<span aria-hidden=\"true\"></span>",
    css=":host { display: none; height: 0; overflow: hidden; }",
    js=_BRIDGE_JS,
)


def mount_auth_bridge(
    *, base_url: str, action: str, nonce: str, token: str | None = None
) -> Any:
    """Mount trusted static JavaScript and return its state values."""
    return _bridge_component(
        data={"baseUrl": base_url, "action": action, "nonce": nonce, "token": token},
        key="oj-auth-bridge",
        on_ticket_result_change=lambda: None,
        on_status_change=lambda: None,
    )
