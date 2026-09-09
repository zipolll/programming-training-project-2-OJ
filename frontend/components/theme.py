"""Central, fixed-light design system for the training workspace."""

import streamlit as st

GLOBAL_CSS = r"""
<style>
:root {
  --oj-primary: #087e96;
  --oj-primary-dark: #066579;
  --oj-ink: #203449;
  --oj-muted: #607284;
  --oj-line: #dce4ea;
  --oj-canvas: #f3f6f8;
  --oj-surface: #ffffff;
  --oj-tint: #eaf4f6;
  --oj-success: #18794e;
  --oj-warning: #946200;
  --oj-danger: #c13c45;
  --oj-shadow: 0 3px 12px rgba(32, 52, 73, .045);
  --oj-font: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
}
:root, .stApp, [data-baseweb="popover"] {
  color-scheme: light;
  --text-color: #203449;
  --background-color: #f3f6f8;
  --secondary-background-color: #ffffff;
}
.stApp { background: var(--oj-canvas); color: var(--oj-ink); }
.stApp, .stApp input, .stApp textarea, .stApp button {
  font-family: var(--oj-font);
}
[data-testid="stHeader"] { background: var(--oj-canvas); }
[data-testid="stMainBlockContainer"] {
  max-width: 1320px; padding: 5rem 2.5rem 4rem;
  container-name: workspace; container-type: inline-size;
}

[data-testid="stMarkdownContainer"] { overflow-wrap: anywhere; }
[data-testid="stMarkdownContainer"] p { line-height: 1.75; }
[data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"] p,
[data-testid="stButton"] button p,
[data-testid="stFormSubmitButton"] button p { font-size: 16px; }
[data-testid="stCaptionContainer"] p { color: var(--oj-muted); font-size: 14px; }
[data-testid="stHeaderActionElements"], a.anchor-link { display: none !important; }

/* AI authoring keeps the prompt central and the generated problem readable. */
.st-key-oj_agent_composer {
  background: var(--oj-surface); border: 1px solid var(--oj-line);
  border-top: 3px solid var(--oj-primary); border-radius: 12px;
  padding: 1.5rem; margin: .5rem 0 1rem;
}
.st-key-oj_agent_composer textarea {
  font-size: 17px; line-height: 1.8; background: var(--oj-surface);
}
.st-key-oj_agent_conversation {
  border: 1px solid var(--oj-line); background: var(--oj-surface); border-radius: 10px;
}
[class*="_conditions"] button { border-radius: 18px; }
.st-key-agent_nav_selection { margin-bottom: .35rem; }
.st-key-oj_agent_navigation .st-key-agent_nav_selection button {
  border: 0 !important; border-bottom: 2px solid transparent !important;
  border-radius: 0 !important; background: transparent !important;
  color: var(--oj-muted) !important; padding: .45rem .8rem; min-height: 40px;
}
.st-key-oj_agent_navigation .st-key-agent_nav_selection
  button:is([aria-pressed="true"], [aria-checked="true"]) {
  color: var(--oj-primary) !important; background: transparent !important;
  border-bottom-color: var(--oj-primary) !important;
}
.st-key-agent_nav_selection button p { font-size: 15px; }
.st-key-oj_agent_toolbar {
  padding: 0 0 1rem; margin-bottom: .5rem;
  border-bottom: 1px solid var(--oj-line);
}
.st-key-agent_viewport { display: none; }
.st-key-agent_view_content .st-key-agent_back_history button {
  border: 0; background: transparent; padding-left: 0;
}
.st-key-oj_agent_overview, .st-key-oj_agent_workspace {
  background: var(--oj-surface); border: 1px solid var(--oj-line);
  border-radius: 12px; padding: 24px; margin-bottom: 4px;
  gap: 20px;
}
.st-key-oj_agent_overview .oj-agent-title {
  font-family: var(--oj-font); color: var(--oj-ink); font-size: 24px;
  font-weight: 650; line-height: 1.4; padding: 0; margin: 0;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  overflow: hidden; overflow-wrap: anywhere; white-space: pre-wrap;
}
.st-key-oj_agent_version_tools [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important; align-items: flex-end; gap: 12px;
}
.st-key-oj_agent_version_tools [data-testid="stColumn"] {
  min-width: 0 !important; width: auto !important; flex: 1 1 auto !important;
}
.st-key-oj_agent_version_tools [data-testid="stColumn"]:last-child {
  flex: 0 0 88px !important;
}
.st-key-oj_agent_version_tools [data-baseweb="select"] > div,
.st-key-oj_agent_version_tools .react-aria-ComboBox > [role="group"],
.st-key-oj_agent_version_tools [data-testid="stPopover"] button {
  min-height: 44px; height: 44px; box-sizing: border-box;
}
.st-key-oj_agent_version_tools .react-aria-ComboBox :is(input, button) { height: 42px; }
.st-key-oj_agent_requirement_summary { gap: 8px; }
.st-key-oj_agent_overview .oj-agent-request-preview {
  white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.75;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3;
  overflow: hidden; font-size: 16px; color: var(--oj-ink);
}
.st-key-oj_agent_requirement_summary [data-testid="stText"] {
  white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--oj-font);
}
.st-key-oj_agent_failure {
  background: #fbf8eb; padding: 16px; border-radius: 8px; gap: 12px;
}
.st-key-oj_agent_failure .oj-agent-status-message {
  color: var(--oj-warning); margin: 0; line-height: 1.6;
}
.st-key-oj_agent_document { padding: 0; min-width: 0; }
.st-key-oj_agent_document .oj-agent-empty {
  color: var(--oj-muted); padding: 12px 0; margin: 0; line-height: 1.75;
}
.st-key-oj_agent_task_information {
  border-top: 1px solid var(--oj-line); padding-top: 16px;
}
.st-key-oj_agent_document [data-testid="stMarkdownContainer"] {
  max-width: 80ch;
}
.st-key-oj_agent_ai_bottom {
  background: var(--oj-surface); border: 1px solid var(--oj-line);
  border-radius: 12px; padding: 24px; gap: 16px;
}
.st-key-oj_agent_retry_panel { min-width: 0; }
.st-key-oj_agent_conversation [data-testid="stVerticalBlock"] { gap: .7rem; }
.oj-chat-row { display: flex; align-items: flex-start; gap: 10px; }
.oj-chat-row.oj-chat-user { flex-direction: row-reverse; }
.oj-chat-avatar {
  flex: 0 0 32px; width: 32px; height: 32px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; user-select: none;
}
.oj-chat-assistant .oj-chat-avatar { background: var(--oj-tint); color: var(--oj-primary); }
.oj-chat-user .oj-chat-avatar { background: #e8eefb; color: #365c9c; }
.oj-chat-bubble {
  max-width: min(72ch, 78%); padding: 10px 14px; border-radius: 12px;
  background: #edf6f8; color: var(--oj-ink); white-space: pre-wrap;
  overflow-wrap: anywhere; line-height: 1.7; font-size: 15px; text-align: left;
}
.oj-chat-user .oj-chat-bubble { background: #e9f0fc; }
.oj-chat-clamp {
  display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden;
}
.st-key-oj_agent_editor_actions button { min-height: 44px; }
.st-key-agent_unload_guard { display:none; }
@media (max-width: 700px) {
  .st-key-oj_agent_composer { padding: 1rem; }
  .st-key-oj_agent_overview, .st-key-oj_agent_workspace { padding: 16px; }
  .st-key-oj_agent_ai_bottom { padding: 16px; }
  .oj-chat-bubble { max-width: 88%; }
  .st-key-oj_agent_overview .oj-agent-title { font-size: 22px; }
  .st-key-oj_agent_document [role="tablist"] { gap: .65rem; }
  .st-key-oj_agent_document [role="tab"] { padding-inline: .1rem; }
  .st-key-oj_agent_navigation [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: .5rem; }
  .st-key-oj_agent_navigation [data-testid="stColumn"] {
    min-width: 0 !important; width: auto !important; flex: 1 1 auto !important;
  }
  .st-key-oj_agent_navigation [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
  .st-key-agent_nav_selection button { padding-inline: .45rem; }
  .st-key-agent_settings_link button { padding-inline: .5rem; }
}
@media (max-width: 1000px) {
  .st-key-oj_agent_task_heading > [data-testid="stHorizontalBlock"] {
    flex-direction: column; gap: 16px;
  }
  .st-key-oj_agent_task_heading > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 auto !important; min-width: 0 !important;
  }
}

/* Existing native navigation remains the only navigation control. */
[data-testid="stSidebar"] {
  background: var(--oj-surface); border-right: 1px solid var(--oj-line);
}
[data-testid="stSidebarNav"]::before {
  content: "OJ　编程训练";
  display: block; margin: 0 1.5rem 1.75rem;
  color: var(--oj-ink); font-size: 22px; font-weight: 750;
}
[data-testid="stSidebarNavLink"] {
  margin: 2px 12px; border-radius: 10px; color: var(--oj-muted);
}
[data-testid="stSidebarNavLink"] p { font-size: 15px; font-weight: 500; }
[data-testid="stSidebarNavLink"]:hover { background: var(--oj-canvas); }
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: var(--oj-tint); color: var(--oj-primary-dark);
  box-shadow: inset 3px 0 var(--oj-primary);
}
[data-testid="stSidebarNavLink"][aria-current="page"] p { font-weight: 700; }
[data-testid="stSidebarNavSeparator"] { border-color: var(--oj-line); }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
  border-top: 1px solid var(--oj-line); padding-top: 1rem;
}

/* Page headings are typography, not another card. IDs remain useful context. */
.oj-hero { padding: 0; margin: 0 0 .5rem; }
.oj-hero h1 {
  margin: 0; padding: 0; color: var(--oj-ink);
  font-size: 32px; font-weight: 700; line-height: 1.4; letter-spacing: -.025em;
}
.oj-hero p { margin: .5rem 0 0; max-width: 48rem; color: var(--oj-muted); font-size: 14px; }
.oj-hero__eyebrow { margin: 0 0 .5rem; color: var(--oj-muted); font-size: 14px; }
.oj-hero--home { padding: 1rem 0 2rem; }
.oj-hero--home h1 { max-width: 36rem; font-size: 40px; }
.oj-section-title { margin: 0; }
.oj-section-title h2 {
  margin: 0; padding: 0 !important; color: var(--oj-ink);
  font-size: 20px; font-weight: 600; line-height: 1.5;
}
.oj-section-title p { margin: .25rem 0 0; color: var(--oj-muted); font-size: 14px; }
.oj-feature-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 2rem; margin: .5rem 0 1rem;
}
.oj-feature-card {
  display: grid; grid-template-columns: 40px 1fr;
  column-gap: 1rem; padding: 1.5rem 0; border-bottom: 1px solid var(--oj-line);
}
.oj-feature-card__icon {
  grid-row: span 2; display: grid; place-items: start center;
  color: var(--oj-primary); padding-top: 3px;
}
.oj-feature-card__icon svg { width: 28px; height: 28px; }
.oj-feature-card h3 { margin: 0; color: var(--oj-ink); font-size: 20px; font-weight: 650; }
.oj-feature-card p {
  margin: .5rem 0 0;
  color: var(--oj-muted);
  font-size: 14px;
  line-height: 1.75;

}
.oj-info-card { padding: .75rem 0; }
.oj-info-card__label { color: var(--oj-muted); font-size: 14px; }
.oj-info-card__value {
  margin-top: .25rem; color: var(--oj-ink); font-size: 20px;
  font-weight: 650; font-variant-numeric: tabular-nums; overflow-wrap: anywhere;
}
.oj-empty {
  padding: 2rem; border: 1px dashed var(--oj-line); border-radius: 10px;
  color: var(--oj-muted); text-align: center; background: var(--oj-surface);
}
.oj-badges { display: flex; flex-wrap: wrap; gap: .5rem; margin: .25rem 0; }
.oj-badge {
  display: inline-flex; align-items: center; padding: .2rem .65rem;
  border: 1px solid var(--oj-line); border-radius: 999px;
  color: var(--oj-muted); background: var(--oj-surface);
  font-size: 14px; font-weight: 500; line-height: 1.5; overflow-wrap: anywhere;
}
.oj-badge--cyan { color: #066579; background: #eaf4f6; border-color: #c1dfe5; }
.oj-badge--green { color: #18794e; background: #edf7f1; border-color: #c9e4d5; }
.oj-badge--orange, .oj-badge--yellow {
  color: #946200; background: #fff7e7; border-color: #ecdcba;
}
.oj-badge--red { color: #c13c45; background: #fff1f1; border-color: #f0cfd2; }
.oj-badge--blue { color: #285eaa; background: #eef4fc; border-color: #d0def0; }
.oj-badge--purple { color: #675398; background: #f4f1f9; border-color: #ddd5ed; }
.oj-badge--gray { color: var(--oj-muted); background: var(--oj-canvas); }
.oj-badge--pending::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; margin-right: 6px;
}

/* Compact, continuous tables. Keep native row buttons and selection widgets. */
div[class*="st-key-oj_table_"]:not([class*="st-key-oj_table_header_"]) {
  border: 1px solid var(--oj-line); border-radius: 16px;
  box-shadow: var(--oj-shadow); background: var(--oj-surface); overflow: hidden; gap: 0 !important;
}
div[class*="st-key-oj_table_header_"] {
  padding: .75rem 1rem; background: #edf2f5; border-bottom: 1px solid var(--oj-line);
}
div[class*="st-key-oj_record_"] {
  padding: 1rem; border-bottom: 1px solid var(--oj-line); gap: .35rem !important;
}
div[class*="st-key-oj_record_"]:hover { background: #f6fafb; }
div[class*="st-key-oj_table_"] [data-testid="stHorizontalBlock"] { align-items: center; gap: 1rem; }
div[class*="st-key-oj_table_"] [data-testid="stColumn"] { min-width: 0; margin-block: 0; }
div[class*="st-key-oj_table_"] [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
  gap: 0 !important;

}
div[class*="st-key-oj_table_"] [data-testid="stMarkdownContainer"] p { margin: 0; }
div[class*="st-key-oj_table_"] [data-testid="stMarkdownContainer"],
div[class*="st-key-oj_panel_heading_"] [data-testid="stMarkdownContainer"] { margin: 0 !important; }
div[class*="st-key-oj_table_"] .oj-badges { margin: 0; gap: .3rem; }
div[class*="st-key-oj_table_"] [data-testid="stButton"] button {
  min-height: 36px; padding: .25rem 0; margin: 0; border: 0;
  border-radius: 4px; background: transparent; box-shadow: none;
  color: var(--oj-primary-dark); text-align: left; justify-content: flex-start;
}
div[class*="st-key-oj_table_"] [data-testid="stButton"] button:hover {
  text-decoration: underline; background: transparent;
}
div[class*="st-key-oj_table_"] [data-testid="stButton"] button p {
  font-weight: 600; line-height: 1.5; color: inherit; overflow-wrap: anywhere;
}
.oj-cell-text {
  color: var(--oj-ink); font-size: 16px; line-height: 1.5;
  overflow-wrap: anywhere; font-variant-numeric: tabular-nums;
}
.oj-cell-text--strong { font-weight: 650; }
.oj-cell-text--muted { color: var(--oj-muted); font-size: 14px; }
.oj-cell-text--timestamp { white-space: pre-line; font-size: 14px; }
.oj-cell-text--success { color: var(--oj-success); }
.oj-cell-text--failure { color: var(--oj-danger); }
div[class*="st-key-oj_table_header_"] .oj-cell-text { font-size: 14px; color: var(--oj-muted); }
.oj-field-label,
div[class*="st-key-oj_table_"] [data-testid="stElementContainer"]:has(.oj-field-label) {
  display: none;

}

/* Panels mark editable or independently actionable sections; no nested shadows. */
div[class*="st-key-oj_panel_"]:not(
  [class*="st-key-oj_panel_heading_"], [class*="st-key-oj_panel_body_"]
) {
  border: 1px solid var(--oj-line); border-radius: 16px;
  box-shadow: var(--oj-shadow); background: var(--oj-surface); gap: 0 !important;
}
div[class*="st-key-oj_panel_heading_"] { padding: 1.5rem 1.5rem 0; }
div[class*="st-key-oj_panel_heading_"] .oj-section-title { margin: 0; }
div[class*="st-key-oj_panel_heading_"] .oj-section-title h2 { font-size: 20px; }
div[class*="st-key-oj_panel_body_"] { padding: 1rem 1.5rem 1.5rem; }
div[class*="st-key-oj_panel_toolbar_"] {
  border-radius: 12px !important; background: #f8fbfc !important; box-shadow: none !important;
}
div[class*="st-key-oj_panel_toolbar_"] div[class*="st-key-oj_panel_heading_"] {
  padding: 1rem 1.25rem 0;

}
div[class*="st-key-oj_panel_toolbar_"] div[class*="st-key-oj_panel_body_"] { padding: 1.25rem; }
div[class*="st-key-oj_panel_warning_"] { border-color: #ecdcba; }
div[class*="st-key-oj_panel_warning_"] .oj-section-title h2 { color: var(--oj-warning); }
[class*="st-key-bank_link_card_"] {
  padding: 1.25rem 1.5rem; border: 1px solid var(--oj-line);
  border-radius: 16px; background: var(--oj-surface); box-shadow: var(--oj-shadow);
}
[class*="st-key-bank_link_card_"] [data-testid="stButton"] button {
  padding: 0; min-height: 36px; color: var(--oj-primary-dark);
  background: transparent; border: 0; text-align: left;
}
[class*="st-key-bank_link_card_"] [data-testid="stButton"] button p {
  font-size: 20px;
  font-weight: 600;

}
[class*="st-key-bank_link_card_"] [data-testid="stButton"] button:hover {
  text-decoration: underline;

}

/* Reading surface: comfortable measure, typography and two-column examples. */
.st-key-problem_statement, [class*="st-key-agent_problem_detail"] {
  background: var(--oj-surface); border: 1px solid var(--oj-line) !important;
  border-radius: 16px; padding: 1.5rem 2rem; box-shadow: var(--oj-shadow);
}
.st-key-problem_statement { min-width: 0; }
.st-key-problem_statement > div { max-width: 840px; margin-inline: auto; }
.st-key-problem_statement .oj-section-title { margin-top: 1.25rem; }
.st-key-problem_statement [data-testid="stMarkdownContainer"] p { line-height: 1.85; }
.st-key-problem_metadata { gap: 0 !important; }
[class*="st-key-problem_resources"] {
  border-bottom: 1px solid var(--oj-line); padding-bottom: .5rem;
}
code, pre { font-family: "Cascadia Code", Consolas, monospace !important; }
[data-testid="stCode"], [data-testid="stCode"] pre { background: #f3f6f8 !important; }
[data-testid="stCode"] pre { overflow-x: auto; border-radius: 10px; }
[data-testid="stCode"] code { font-size: 14px; }

/* Forms and portals use the same fixed-light palette as the page. */
[data-testid="stForm"] {
  padding: 1.5rem; border: 1px solid var(--oj-line);
  border-radius: 16px; background: var(--oj-surface);
}
[data-testid="stForm"]:has(div[class*="st-key-oj_panel_"]),
div[class*="st-key-oj_panel_body_"] [data-testid="stForm"] {
  padding: 0; border: 0; border-radius: 0; background: transparent;
}
[data-testid="stWidgetLabel"] p { color: var(--oj-ink); font-weight: 600; }
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="textarea"],
.stApp [data-testid="stTextInputRootElement"], .stApp [data-testid="stTextAreaRootElement"],
.stApp [data-testid="stNumberInputContainer"],
.stApp [data-testid="stSelectbox"] .react-aria-ComboBox > [role="group"] {
  border-radius: 10px; border: 1px solid #8193a3; background: var(--oj-surface);
}
input, textarea {
  color: var(--oj-ink) !important; -webkit-text-fill-color: var(--oj-ink) !important;
  background-color: var(--oj-surface); caret-color: var(--oj-primary); font-size: 16px;
}
input::placeholder, textarea::placeholder {
  color: var(--oj-muted) !important; -webkit-text-fill-color: var(--oj-muted) !important;
  opacity: 1;
}
[data-baseweb="select"] > div:focus-within,
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stSelectbox"] .react-aria-ComboBox > [role="group"]:focus-within {
  border-color: var(--oj-primary); outline: 2px solid var(--oj-primary); outline-offset: 2px;
}
[data-baseweb="popover"] > div, [data-baseweb="menu"], [role="listbox"], [role="dialog"] {
  background: var(--oj-surface); color: var(--oj-ink); border-color: var(--oj-line);
}
[data-baseweb="menu"] li, [role="option"] { color: var(--oj-ink); }
[data-baseweb="menu"] li:hover, [role="option"][aria-selected="true"] {
  background: var(--oj-tint);

}

/* Buttons answer actions with colour and focus, never movement. */
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button, [data-testid="stLinkButton"] a,
[data-testid="stPopover"] button {
  min-height: 44px; border-radius: 10px; border: 1px solid #8b9baa;
  background: var(--oj-surface); color: var(--oj-ink); font-weight: 600;
}
[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover,
[data-testid="stDownloadButton"] button:hover, [data-testid="stLinkButton"] a:hover,
[data-testid="stPopover"] button:hover {
  color: var(--oj-primary-dark); border-color: var(--oj-primary); background: var(--oj-tint);
}
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--oj-primary); color: #fff; border-color: var(--oj-primary);
}
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--oj-primary-dark); border-color: var(--oj-primary-dark); color: #fff;
}
button[data-testid="stBaseButton-primary"] p,
button[data-testid="stBaseButton-primaryFormSubmit"] p { color: inherit; }
button:disabled { opacity: .55; cursor: not-allowed; }
button:focus-visible, a:focus-visible, [role="radio"]:focus-visible,
[data-baseweb="tab"]:focus-visible {
  outline: 2px solid var(--oj-primary) !important; outline-offset: 3px;
}

/* Authoring views remain native controls; a selected view is not task progress. */
[data-testid="stSegmentedControl"] [role="radiogroup"],
[data-testid="stButtonGroup"] [role="radiogroup"] {
  display: flex; flex-wrap: wrap; gap: .5rem;
}
[data-testid="stSegmentedControl"] button,
[data-testid="stButtonGroup"] button {
  min-height: 44px; padding: .6rem 1.25rem; border-radius: 10px !important;
  border: 1px solid var(--oj-line); background: var(--oj-surface); color: var(--oj-ink);
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-checked="true"],
[data-testid="stButtonGroup"] button[aria-pressed="true"],
[data-testid="stButtonGroup"] button[aria-checked="true"] {
  color: #fff !important; background: var(--oj-primary) !important;
  border-color: var(--oj-primary) !important;
}
[data-testid="stSegmentedControl"] button :is(div, span, p),
[data-testid="stButtonGroup"] button :is(div, span, p) { color: inherit; }
[data-testid="stSegmentedControl"] button p, [data-testid="stButtonGroup"] button p {
  color: inherit; font-size: 16px; white-space: normal; line-height: 1.5;
}
[class*="problem_authoring_mode"] [role="radiogroup"] { margin: .25rem 0 .5rem; }
[class*="problem_authoring_mode"] button { min-height: 40px; padding: .4rem .9rem; }
[class*="problem_authoring_mode"] [role="radiogroup"] button p {
  font-size: 16px;
  font-weight: 600;

}
[class*="agent_active_view"] [role="radiogroup"] {
  padding: .35rem;
  background: #e9eff2;
  border-radius: 12px;
  width: fit-content;

}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 1.5rem;
  border-bottom: 1px solid var(--oj-line);

}
[data-testid="stTabs"] [data-baseweb="tab"] {
  padding: .75rem 0; border-radius: 0; background: transparent !important; color: var(--oj-muted);
}
[data-testid="stTabs"] [aria-selected="true"] {
  color: var(--oj-primary-dark);
  border-bottom: 2px solid var(--oj-primary);

}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
[data-testid="stMetric"] { padding: .5rem 0; }
[data-testid="stMetricLabel"] p { color: var(--oj-muted); font-size: 14px; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] :is(div, p) {
  color: var(--oj-ink); font-size: 30px; font-weight: 650; line-height: 1.35;
}
[data-testid="stExpander"], [data-testid="stDataFrame"] {
  border: 1px solid var(--oj-line); border-radius: 16px; background: var(--oj-surface);
}
[data-testid="stExpander"] details { background: var(--oj-surface); }
[data-testid="stAlert"] { border-radius: 10px; }
.oj-timeline {
  margin: .25rem 0; padding: .25rem 0 .75rem 1rem; border-left: 2px solid var(--oj-line);
}
.oj-timeline__meta { color: var(--oj-muted); font-size: 14px; }
.oj-timeline__message { margin-top: .25rem; color: var(--oj-ink); font-size: 16px; }
.oj-page-number {
  display: flex; align-items: center; justify-content: center;
  min-height: 44px; color: var(--oj-muted); font-size: 1.08rem; white-space: nowrap;
}
[class*="_pagination"] [data-testid="stHorizontalBlock"] {
  align-items: center; justify-content: center; gap: .35rem;
  width: fit-content; max-width: 100%; margin: .5rem auto 0;
}
[class*="_pagination"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
}
[class*="_pagination"] [data-testid="stButton"] button { min-width: 40px; padding-inline: .6rem; }
[class*="_pagination"] [data-testid="stMarkdownContainer"] { margin: 0; }

/* Keyed native layout groups own their spacing; HTML has no paragraph compensation. */
[data-testid="stMarkdownContainer"]:has(.oj-hero),
[data-testid="stMarkdownContainer"]:has(.oj-section-title),
[data-testid="stMarkdownContainer"]:has(.oj-info-card),
[data-testid="stMarkdownContainer"]:has(.oj-badges),
[data-testid="stMarkdownContainer"]:has(.oj-empty) { margin: 0 !important; }
[class*="st-key-oj_page_heading_"] { margin-bottom: .5rem; }
[class*="st-key-oj_page_heading_"] .oj-hero { margin: 0; }
[class*="st-key-oj_form_row_"] { min-width: 0; }
[class*="st-key-oj_form_row_"] > div > [data-testid="stHorizontalBlock"],
[class*="st-key-oj_form_row_"] > [data-testid="stHorizontalBlock"] { gap: 1rem; }
.st-key-oj_bank_grid {
  display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.25rem !important; align-items: stretch;
}
.st-key-oj_bank_grid > div { min-width: 0; width: 100%; height: 100%; }
[class*="st-key-bank_link_card_"] { height: 100%; gap: .75rem !important; min-width: 0; }
[class*="st-key-bank_link_card_"]:has(button:hover),
[class*="st-key-bank_link_card_"]:focus-within {
  border-color: #8ebbc4; box-shadow: 0 5px 16px rgba(32,52,73,.08);
}
[class*="st-key-bank_link_card_"] button p { overflow-wrap: anywhere; white-space: normal; }
[class*="st-key-oj_bank_description_"] {
  height: 3rem; min-height: 3rem;
}
[class*="st-key-oj_bank_description_"] p {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; line-height: 1.5rem; margin: 0 !important;
}
.stApp [data-testid="stCaptionContainer"] { opacity: 1; }
.stApp [data-testid="stCaptionContainer"] p { color: var(--oj-muted) !important; }
[class*="st-key-oj_catalogue_meta_"] { margin-top: .25rem; }
[class*="st-key-oj_catalogue_meta_"] .oj-badge {
  border: 0; border-radius: 5px; padding: .12rem .5rem; font-size: 13px;
}
.st-key-oj_problem_facts, .st-key-oj_recent_submissions {
  padding: 1.25rem; background: var(--oj-surface); border: 1px solid var(--oj-line);
  border-radius: 16px; box-shadow: var(--oj-shadow);
}
.st-key-oj_problem_facts .oj-info-card { padding: .25rem 0; }
.st-key-oj_problem_facts .oj-info-card__value { font-size: 16px; font-weight: 500; }
.st-key-oj_problem_reading { gap: 1.5rem; }
.st-key-oj_problem_facts { padding: 1.5rem 2rem; }
.st-key-oj_problem_actions { gap: .5rem; }
.st-key-oj_split_profile > div > [data-testid="stHorizontalBlock"] { gap: 1.5rem; }
[class*="st-key-oj_profile_fields_"] .oj-info-card { padding: .25rem 0; }
[class*="st-key-oj_profile_fields_"] .oj-info-card__value { font-size: 20px; }
[class*="st-key-oj_profile_fields_"] [data-testid="stHorizontalBlock"] { gap: 1rem; }
[class*="st-key-oj_profile_fields_"] [data-testid="stColumn"] {
  flex: 1 1 calc(50% - .5rem) !important;
  width: calc(50% - .5rem) !important; min-width: 0 !important;
}
.st-key-oj_panel_body_agent_request .oj-info-card { padding: .25rem 0; }
.st-key-oj_panel_body_agent_request .oj-info-card__value {
  font-size: 16px; font-weight: 500; line-height: 1.75; white-space: pre-wrap;
}
.st-key-oj_agent_long_requirements .oj-info-card__value { font-weight: 400; }
[class*="st-key-detail_bank_add_"] button {
  min-height: 36px; padding: .375rem .75rem; font-weight: 500;
}
[class*="st-key-detail_bank_add_"] button p { font-size: 14px; font-weight: 500; }
.st-key-oj_recent_submissions .oj-section-title h2 { font-size: 18px; }
.st-key-oj_recent_submissions [class*="st-key-oj_table_"] { box-shadow: none; }
.st-key-oj_recent_submissions [class*="st-key-oj_table_header_"] { display: none; }
.st-key-oj_recent_submissions [class*="st-key-oj_record_"] { padding: .75rem; }
.st-key-oj_recent_submissions .oj-badge { font-size: 13px; padding: .15rem .35rem; }
.st-key-oj_recent_submissions [class*="st-key-oj_table_"] [data-testid="stHorizontalBlock"] {
  gap: .5rem;

}
.st-key-oj_result_summary {
  padding: 1.25rem 1.5rem; background: var(--oj-surface);
  border: 1px solid var(--oj-line); border-radius: 16px; box-shadow: var(--oj-shadow);
}
.st-key-oj_home_intro {
  padding: 2rem; background: var(--oj-surface); border-radius: 20px;
  border: 1px solid var(--oj-line); box-shadow: var(--oj-shadow);
}
.st-key-oj_home_status { padding: 1.5rem; border-radius: 16px; background: var(--oj-tint); }
.st-key-oj_home_intro .oj-hero--home { padding: 0; }
.st-key-oj_home_intro .oj-hero--home h1 { font-size: clamp(30px, 3vw, 40px); }
[data-testid="stCaptionContainer"] p, [data-testid="stCaption"] {
  color: var(--oj-muted); font-size: 14px;
}
[data-testid="stButton"] button, [data-testid="stPopover"] button,
[data-testid="stFormSubmitButton"] button, [class*="st-key-bank_link_card_"] {
  transition: background-color 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

/* Breakpoints follow available content width rather than the screen or sidebar state. */
@container workspace (max-width: 959px) {
  .st-key-oj_bank_grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  [class*="st-key-oj_split_"] > div > [data-testid="stHorizontalBlock"],
  [class*="st-key-oj_split_"] > [data-testid="stHorizontalBlock"] {
    flex-direction: column; align-items: stretch; gap: 1.5rem;
  }
  [class*="st-key-oj_split_"] > div > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
  [class*="st-key-oj_split_"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 auto !important; min-width: 0 !important;
  }
  .st-key-oj_split_profile [class*="st-key-oj_panel_default_profile_"] {
    height: auto; flex: 0 0 auto;
  }
}
@container workspace (max-width: 699px) {
  .st-key-oj_problem_summary [data-testid="stHorizontalBlock"],
  .st-key-oj_problem_credits [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 1rem; }
  .st-key-oj_problem_summary [data-testid="stColumn"],
  .st-key-oj_problem_credits [data-testid="stColumn"] {
    flex: 1 1 calc(50% - .5rem) !important;
    width: calc(50% - .5rem) !important; min-width: 0 !important;
  }
  .st-key-oj_problem_actions { justify-content: flex-start; }
  [class*="st-key-oj_form_row_"] [data-testid="stHorizontalBlock"],
  [class*="st-key-oj_panel_body_"] > div > [data-testid="stHorizontalBlock"],
  [class*="st-key-oj_page_heading_"] > div > [data-testid="stHorizontalBlock"] {
    flex-direction: column; align-items: stretch;
  }
  [class*="st-key-oj_form_row_"] [data-testid="stColumn"],
  [class*="st-key-oj_panel_body_"] >
    div >
    [data-testid="stHorizontalBlock"] >
    [data-testid="stColumn"],
  [class*="st-key-oj_page_heading_"] >
    div >
    [data-testid="stHorizontalBlock"] >
    [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 auto !important; min-width: 0 !important;
  }
  [class*="st-key-oj_page_heading_"] [data-testid="stHorizontalBlock"] {
  justify-content: flex-start;

}
}
@container workspace (max-width: 639px) {
  .st-key-oj_bank_grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding: 4.5rem 1.5rem 3rem; }
}
@media (max-width: 700px) {
  [data-testid="stMainBlockContainer"] { padding: 4.5rem 1rem 3rem; }
  .oj-hero h1 { font-size: 28px; }
  .oj-feature-grid { grid-template-columns: 1fr; }
  div[class*="st-key-oj_table_header_"] { display: none; }
  div[class*="st-key-oj_record_"] [data-testid="stHorizontalBlock"] {
    flex-direction: column; align-items: stretch; gap: .65rem;
  }
  div[class*="st-key-oj_record_"] [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 auto !important; min-width: 0 !important;
  }
  div[class*="st-key-oj_record_"] [data-testid="stElementContainer"]:has(.oj-field-label) {
  display: block;

}
  .oj-field-label { display: block; color: var(--oj-muted); font-size: 13px; }
  div[class*="st-key-oj_panel_heading_"] { padding: 1rem 1rem 0; }
  div[class*="st-key-oj_panel_body_"] { padding: 1rem; }
  .st-key-problem_statement, .st-key-oj_home_intro, .st-key-oj_problem_facts { padding: 1.25rem; }
  [class*="st-key-detail_bank_add_"] button { min-height: 44px; }
  .st-key-oj_result_summary > div > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-oj_result_summary >
    div >
    [data-testid="stHorizontalBlock"] >
    [data-testid="stColumn"]:first-child {
    flex: 1 0 100% !important; width: 100% !important;
  }
  .st-key-oj_result_summary >
    div >
    [data-testid="stHorizontalBlock"] >
    [data-testid="stColumn"]:not(:first-child) {
    flex: 1 1 40% !important; width: 40% !important; min-width: 0 !important;
  }
  [class*="problem_authoring_mode"] [role="radiogroup"] button p { font-size: 15px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important; animation-iteration-count: 1 !important;
    transition-duration: .01ms !important; scroll-behavior: auto !important;
  }
}
</style>
"""


def apply_theme() -> None:
    """Inject styles without invoking the Markdown parser on every rerun."""
    st.html(GLOBAL_CSS)
