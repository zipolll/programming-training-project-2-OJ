"""Local syntax editor with tab-scoped drafts and atomic submission events."""

from pathlib import Path

import streamlit as st

from frontend.components.common import show_error
from frontend.navigation import open_submission, restore_widget, save_widgets
from frontend.session import current_user


def code_language(value: str) -> str | None:
    normalized = value.lower()
    if normalized.startswith(("python", "py")):
        return "python"
    if normalized.startswith(("cpp", "c++")):
        return "cpp"
    return None


def _component():
    return st.components.v2.component(
        "oj_code_editor",
        html='<div class="oj-editor"></div><p role="status"></p>'
             '<button type="button">提交评测</button>',
        css="""
        :host { color-scheme: light; display: block; min-width: 0; }
        .oj-editor { border: 1px solid #8193a3; border-radius: 10px; overflow: hidden; }
        button { padding: 12px 24px; border: 0; border-radius: 10px; color: white;
          background: #087e96; cursor: pointer;
          font: 600 16px "PingFang SC", "Microsoft YaHei", sans-serif; min-height: 44px; }
        button:hover { background: #066579; }
        button:focus-visible { outline: 2px solid #087e96; outline-offset: 3px; }
        button:disabled { opacity: .65; cursor: wait; }
        [role=status] { color: #c13c45; font: 14px "Microsoft YaHei", sans-serif; }
        """,
        js=Path(__file__).with_name("editor").joinpath("editor.bundle.js").read_text("utf-8"),
    )


def render_code_submission(api, problem_id: str, languages: list[str], *, key: str) -> None:
    error = st.session_state.pop(f"{key}_editor_error", None)
    if error:
        show_error(RuntimeError(error))
    restore_widget(f"{key}_language", languages[0], options=languages)
    language = st.selectbox("语言", languages, key=f"{key}_language", width=300,
                           on_change=save_widgets, args=(f"{key}_language",))
    user = current_user() or {}
    generation_key = f"{key}_editor_generation"
    generation = st.session_state.get(generation_key, 0)
    result = _component()(
        data={"language": language, "user": user.get("id", "anonymous"),
              "problem": problem_id},
        key=f"{key}_editor_{problem_id}_{language}_{generation}",
        on_submission_change=lambda: None,
    )
    event = getattr(result, "submission", None)
    if not isinstance(event, dict) or not event.get("event_id"):
        return
    handled = f"{key}_last_event"
    if st.session_state.get(handled) == event["event_id"]:
        return
    st.session_state[handled] = event["event_id"]
    try:
        data = api.post("/submissions/", json={
            "problem_id": problem_id, "language": event["language"], "code": event["code"],
        })["data"]
    except Exception as exc:
        st.session_state[f"{key}_editor_error"] = str(exc)
        st.session_state[generation_key] = generation + 1
        st.rerun()
    else:
        open_submission(str(data["submission_id"]))
        st.rerun()
