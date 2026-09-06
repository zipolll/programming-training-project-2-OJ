"""Central visual theme for the Streamlit frontend."""

import streamlit as st

GLOBAL_CSS = r"""
<style>
:root {
  --oj-primary: #5b5cf0;
  --oj-primary-dark: #4647cc;
  --oj-secondary: #06b6d4;
  --oj-accent: #f97316;
  --oj-success: #16a34a;
  --oj-warning: #d97706;
  --oj-danger: #dc2626;
  --oj-ink: #172033;
  --oj-muted: #667085;
  --oj-line: #dfe5f1;
  --oj-surface: rgba(255, 255, 255, 0.94);
  --oj-shadow: 0 14px 35px rgba(73, 80, 135, 0.10);
}

html, body, [class*="css"], .stApp {
  font-family: Inter, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
    system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--oj-ink);
}

.stApp {
  background:
    radial-gradient(circle at 8% 5%, rgba(91, 92, 240, 0.13), transparent 25rem),
    radial-gradient(circle at 92% 15%, rgba(6, 182, 212, 0.11), transparent 23rem),
    linear-gradient(180deg, #f8faff 0%, #f4f7fc 100%);
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppViewContainer"] > .main .block-container {
  max-width: 1260px;
  padding-top: 2.2rem;
  padding-bottom: 4rem;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #ffffff 0%, #f2f4ff 100%);
  border-right: 1px solid rgba(91, 92, 240, 0.14);
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top: 1.25rem; }
[data-testid="stSidebarNav"] span { font-weight: 650; }
[data-testid="stSidebarNavLink"] {
  border-radius: 11px;
  margin: 2px 8px;
  transition: background .18s ease, transform .18s ease, color .18s ease;
}
[data-testid="stSidebarNavLink"]:hover {
  background: rgba(91, 92, 240, 0.09);
  color: var(--oj-primary-dark);
  transform: translateX(3px);
}
[data-testid="stSidebarNavLink"][aria-current="page"] {
  color: #3730a3 !important;
  background: #eef2ff;
  box-shadow: 0 5px 14px rgba(91, 92, 240, 0.11);
}
[data-testid="stSidebarNavLink"][aria-current="page"] * {
  color: #3730a3 !important;
  fill: #3730a3 !important;
}

.oj-hero {
  position: relative;
  overflow: hidden;
  padding: 1.65rem 1.8rem;
  margin: 0 0 1.35rem;
  border: 1px solid rgba(91, 92, 240, 0.18);
  border-radius: 22px;
  background: linear-gradient(125deg, rgba(255,255,255,.98), rgba(239,242,255,.95));
  box-shadow: var(--oj-shadow);
}
.oj-hero::after {
  content: "";
  position: absolute;
  width: 190px;
  height: 190px;
  right: -55px;
  top: -75px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(91,92,240,.24), rgba(6,182,212,.18));
}
.oj-hero--ai {
  color: #fff;
  border: 0;
  background: linear-gradient(125deg, #4f46e5, #7c3aed 55%, #0891b2);
}
.oj-hero--ai::after { background: rgba(255,255,255,.12); }
.oj-hero__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  margin-bottom: .55rem;
  color: var(--oj-primary-dark);
  font-size: .74rem;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.oj-hero--ai .oj-hero__eyebrow { color: #dbeafe; }
.oj-hero h1 {
  position: relative;
  z-index: 1;
  margin: 0;
  color: var(--oj-ink);
  font-size: clamp(1.85rem, 4vw, 2.65rem);
  line-height: 1.12;
  font-weight: 850;
  letter-spacing: -.035em;
}
.oj-hero--ai h1 { color: #fff; }
.oj-hero__icon { margin-right: .45rem; }
.oj-hero p {
  position: relative;
  z-index: 1;
  max-width: 760px;
  margin: .7rem 0 0;
  color: var(--oj-muted);
  font-size: 1rem;
  line-height: 1.75;
}
.oj-hero--ai p { color: rgba(255,255,255,.86); }

.oj-section-title {
  display: flex;
  align-items: flex-start;
  gap: .75rem;
  margin: 1.55rem 0 .8rem;
  padding: .2rem 0 .2rem .2rem;
}
.oj-section-title__icon {
  display: grid;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  flex: 0 0 1.75rem;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(91,92,240,.14), rgba(6,182,212,.16));
  font-size: 1rem;
  line-height: 1;
}
.oj-section-title h2 {
  margin: 0;
  padding: 0 !important;
  min-height: 1.75rem;
  display: flex;
  align-items: center;
  font-size: 1.16rem;
  line-height: 1.75rem;
  font-weight: 800;
}
.oj-section-title p { margin: .12rem 0 0; color: var(--oj-muted); font-size: .83rem; }

/* Streamlit adds permalink controls to headings; these are not useful in this app. */
[data-testid="stHeaderActionElements"],
a.anchor-link {
  display: none !important;
}

.oj-feature-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .9rem;
  margin: 1rem 0 1.5rem;
}
.oj-feature-card, .oj-info-card, .oj-empty {
  border: 1px solid var(--oj-line);
  border-radius: 16px;
  background: var(--oj-surface);
  box-shadow: 0 7px 20px rgba(73,80,135,.07);
}
.oj-feature-card {
  padding: 1.1rem;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
}
.oj-feature-card:hover {
  transform: translateY(-3px);
  border-color: rgba(91,92,240,.32);
  box-shadow: 0 14px 28px rgba(73,80,135,.13);
}
.oj-feature-card__icon { font-size: 1.55rem; }
.oj-feature-card h3 { margin: .55rem 0 .25rem; font-size: 1rem; font-weight: 800; }
.oj-feature-card p { margin: 0; color: var(--oj-muted); font-size: .82rem; line-height: 1.55; }
.oj-info-card { padding: 1rem 1.1rem; margin: .5rem 0; }
.oj-info-card__label { color: var(--oj-muted); font-size: .76rem; font-weight: 700; }
.oj-info-card__value { margin-top: .2rem; font-size: 1.08rem; font-weight: 800; }
.oj-info-card--compact .oj-info-card__label,
.oj-info-card--compact .oj-info-card__value { white-space: nowrap; }
.oj-empty { padding: 2rem; text-align: center; color: var(--oj-muted); }
.oj-empty__icon { display: block; margin-bottom: .5rem; font-size: 2rem; }

.oj-badges { display: flex; flex-wrap: wrap; gap: .45rem; margin: .55rem 0; }
.oj-badge {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  padding: .28rem .65rem;
  border-radius: 999px;
  border: 1px solid rgba(91,92,240,.18);
  color: var(--oj-primary-dark);
  background: rgba(91,92,240,.09);
  font-size: .76rem;
  font-weight: 750;
}
.oj-badge--cyan { color: #0e7490; background: #ecfeff; border-color: #a5f3fc; }
.oj-badge--orange { color: #c2410c; background: #fff7ed; border-color: #fed7aa; }
.oj-badge--green { color: #15803d; background: #f0fdf4; border-color: #bbf7d0; }
.oj-badge--red { color: #b91c1c; background: #fef2f2; border-color: #fecaca; }
.oj-badge--purple { color: #6d28d9; background: #f5f3ff; border-color: #ddd6fe; }
.oj-badge--pending { animation: oj-pulse 1.5s ease-in-out infinite; }

[class*="problem_statement"] {
  background: #ffffff !important;
  color: #111827 !important;
}
[class*="agent_problem_detail"] {
  background: #fff;
  color: #111827;
  border-color: #dbe3f0 !important;
  box-shadow: var(--oj-shadow);
}
[class*="agent_problem_detail"] p,
[class*="agent_problem_detail"] li,
[class*="agent_problem_detail"] h1,
[class*="agent_problem_detail"] h2,
[class*="agent_problem_detail"] h3,
[class*="agent_problem_detail"] h4 { color: #111827 !important; }
[class*="problem_statement"] p,
[class*="problem_statement"] li,
[class*="problem_statement"] h1,
[class*="problem_statement"] h2,
[class*="problem_statement"] h3,
[class*="problem_statement"] h4 { color: #111827 !important; }
[class*="problem_metadata"][data-testid="stVerticalBlock"] {
  gap: 0 !important;
  margin: 0;
  padding: .15rem 0 .9rem;
  border-bottom: 1px solid var(--oj-line);
}
[class*="problem_metadata"] .oj-badges {
  gap: .5rem;
  margin: 0;
}
[class*="problem_metadata"] + [data-testid="stElementContainer"] .oj-section-title {
  margin-top: .4rem;
}

/* Shared table and section contracts. Scope styles to the actual keyed blocks. */
div[class*="st-key-oj_table_"]:not([class*="st-key-oj_table_header_"]) {
  border: 1px solid var(--oj-line);
  border-radius: 16px;
  background: var(--oj-surface);
  box-shadow: 0 7px 20px rgba(73,80,135,.06);
  overflow: hidden;
  gap: 0 !important;
}
div[class*="st-key-oj_table_header_"] {
  background: linear-gradient(110deg, #eef1ff, #f0f9fc);
  padding: .8rem 1rem;
  border-bottom: 1px solid var(--oj-line);
}
div[class*="st-key-oj_record_"] {
  padding: .5rem 1rem;
  border-bottom: 1px solid var(--oj-line);
  gap: .35rem !important;
  transition: background .15s ease;
}
div[class*="st-key-oj_record_"]:hover { background: #f5f7ff; }
div[class*="st-key-oj_table_"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  gap: 1rem;
}
div[class*="st-key-oj_table_"] [data-testid="stColumn"] {
  min-width: 0;
  margin-block: 0;
}
div[class*="st-key-oj_table_"] [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
  gap: 0 !important;
}
div[class*="st-key-oj_table_"] [data-testid="stMarkdownContainer"] p {
  margin: 0;
}
/* Streamlit compensates paragraph spacing with -1rem on the wrapper.
   HTML cells have no paragraph margin: remove that compensation as well. */
div[class*="st-key-oj_table_"] [data-testid="stMarkdownContainer"],
div[class*="st-key-oj_panel_heading_"] [data-testid="stMarkdownContainer"] {
  margin: 0 !important;
}
div[class*="st-key-oj_table_"] .oj-badges {
  margin: 0;
  align-items: center;
  gap: .3rem;
  transform: none;
}
div[class*="st-key-oj_table_"] .oj-badge {
  line-height: 1.4;
  padding: .3rem .65rem;
}
div[class*="st-key-oj_table_"] [data-testid="stButton"] button {
  min-height: 0;
  padding: .3rem 0;
  margin: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  box-shadow: none;
  color: #2563eb;
  text-align: left;
  justify-content: flex-start;
  transform: none;
}
div[class*="st-key-oj_table_"] [data-testid="stButton"] button p {
  font-size: .94rem;
  font-weight: 750;
  line-height: 1.5;
  color: inherit;
  overflow-wrap: anywhere;
}
div[class*="st-key-oj_table_"] [data-testid="stButton"] button:hover {
  color: #1d4ed8;
  text-decoration: underline;
  background: transparent;
  box-shadow: none;
  transform: none;
}
div[class*="st-key-oj_table_"] [data-testid="stButton"] button:focus-visible {
  outline: 3px solid #a5b4fc;
  outline-offset: 3px;
}
.oj-cell-text {
  color: var(--oj-ink);
  font-size: .94rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
}
.oj-cell-text--strong { font-weight: 750; }
.oj-cell-text--muted { color: var(--oj-muted); font-size: .86rem; }
.oj-cell-text--success { color: #15803d; }
.oj-cell-text--failure { color: #b91c1c; }
.oj-field-label { display: none; }
div[class*="st-key-oj_table_"] [data-testid="stElementContainer"]:has(.oj-field-label) {
  display: none;
}
div[class*="st-key-oj_panel_"]:not(
  [class*="st-key-oj_panel_heading_"], [class*="st-key-oj_panel_body_"]
) {
  border: 1px solid var(--oj-line);
  border-radius: 16px;
  background: var(--oj-surface);
  box-shadow: 0 7px 20px rgba(73,80,135,.06);
  gap: 0 !important;
}
div[class*="st-key-oj_panel_heading_"] {
  padding: .8rem 1.1rem;
  border-radius: 15px 15px 0 0;
  border-bottom: 1px solid var(--oj-line);
  background: linear-gradient(110deg, #eef1ff, #f0f9fc);
}
div[class*="st-key-oj_panel_heading_"] .oj-section-title {
  margin: 0;
  padding: 0;
  align-items: center;
}
div[class*="st-key-oj_panel_heading_"] .oj-section-title h2 {
  font-size: 1.02rem;
  font-weight: 750;
}
div[class*="st-key-oj_panel_body_"] { padding: 1rem 1.1rem; }
div[class*="st-key-oj_panel_warning_"] div[class*="st-key-oj_panel_heading_"] {
  background: #fff7ed;
}
div[class*="st-key-oj_panel_toolbar_"] div[class*="st-key-oj_panel_body_"] {
  background: #f8faff;
  border-radius: 0 0 15px 15px;
}
@media (max-width: 700px) {
  div[class*="st-key-oj_table_header_"] { display: none; }
  div[class*="st-key-oj_table_"]:not([class*="st-key-oj_table_header_"]) {
    border: 0;
    background: transparent;
    box-shadow: none;
    overflow: visible;
    gap: .75rem !important;
  }
  div[class*="st-key-oj_record_"] {
    border: 1px solid var(--oj-line) !important;
    border-radius: 13px;
    background: var(--oj-surface);
    padding: .7rem .9rem;
  }
  div[class*="st-key-oj_record_"] [data-testid="stHorizontalBlock"] {
    flex-direction: column;
    align-items: stretch;
    gap: .65rem;
  }
  div[class*="st-key-oj_record_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important;
    flex: 1 1 auto !important;
    min-width: 0 !important;
  }
  div[class*="st-key-oj_record_"] [data-testid="stElementContainer"]:has(.oj-field-label) {
    display: block;
    margin-bottom: .15rem;
  }
  .oj-field-label {
    display: block;
    color: var(--oj-muted);
    font-size: .75rem;
    font-weight: 650;
    line-height: 1.4;
  }
  div[class*="st-key-oj_panel_body_"] { padding: .85rem; }
}
.oj-timeline {
  position: relative;
  margin: .35rem 0 .35rem .45rem;
  padding: .3rem 0 .3rem 1.2rem;
  border-left: 2px solid #c7d2fe;
}
.oj-timeline::before {
  content: "";
  position: absolute;
  left: -5px;
  top: .8rem;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--oj-primary);
}
.oj-timeline__meta { color: var(--oj-primary-dark); font-size: .72rem; font-weight: 750; }
.oj-timeline__message { margin-top: .12rem; color: var(--oj-muted); font-size: .84rem; }

[data-testid="stForm"] {
  padding: 1.15rem 1.2rem 1.25rem;
  border: 1px solid var(--oj-line);
  border-radius: 18px;
  background: rgba(255,255,255,.92);
  box-shadow: 0 9px 26px rgba(73,80,135,.07);
}
/* Forms group submission behavior; inner panels supply their visual boundaries. */
[data-testid="stForm"]:has(div[class*="st-key-oj_panel_"]),
div[class*="st-key-oj_panel_body_"] [data-testid="stForm"] {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
[class*="st-key-bank_link_card_"] {
  padding: 1rem 1.3rem;
  border: 1px solid var(--oj-line);
  border-radius: 16px;
  background: rgba(255,255,255,.88);
}
[class*="st-key-bank_link_card_"] [data-testid="stButton"] button {
  padding: 0;
  color: var(--oj-primary-dark);
  background: transparent;
  border: 0;
  box-shadow: none;
}
[class*="st-key-bank_link_card_"] [data-testid="stButton"] button p {
  font-size: 1.2rem;
  font-weight: 750;
}
[data-testid="stWidgetLabel"] p { color: #28324a; font-weight: 720; }
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-baseweb="select"] > div {
  border-radius: 10px !important;
  border-color: #d8deeb !important;
  background: #fbfcff !important;
  transition: border-color .18s ease, box-shadow .18s ease;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus {
  border-color: var(--oj-primary) !important;
  box-shadow: 0 0 0 3px rgba(91,92,240,.12) !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
  color: #98a2b3 !important;
  font-style: italic;
  opacity: 1;
}
.stButton > button, [data-testid="stFormSubmitButton"] button {
  border-radius: 10px;
  font-weight: 750;
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}
/* Secondary actions use a tinted surface; pagination keeps its neutral buttons. */
[data-testid="stButton"] button[kind="secondary"],
[data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"],
[data-testid="stDownloadButton"] button,
[data-testid="stLinkButton"] a {
  background: #e8eaff;
  border-color: #c7ccfa;
  color: #4338a0;
}
[data-testid="stButton"] button p,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stDownloadButton"] button p,
[data-testid="stLinkButton"] a p {
  font-weight: 650;
}
[class*="_pagination"] [data-testid="stButton"] button[kind="secondary"] {
  background: #fff;
  border-color: #d1d5db;
  color: #303544;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {
  transform: translateY(-1px);
  border-color: var(--oj-primary);
  box-shadow: 0 7px 16px rgba(91,92,240,.17);
}
.stButton > button:focus-visible,
[data-testid="stFormSubmitButton"] button:focus-visible,
[data-testid="stSidebarNavLink"] a:focus-visible,
[data-baseweb="tab"]:focus-visible {
  outline: 3px solid rgba(6,182,212,.55) !important;
  outline-offset: 3px;
  box-shadow: 0 0 0 5px rgba(6,182,212,.12) !important;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"],
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
  color: #fff;
  border: 0;
  background: linear-gradient(115deg, var(--oj-primary), #7c3aed);
}
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  color: #fff;
  background: linear-gradient(115deg, var(--oj-primary-dark), #6d28d9);
}
[data-testid="stSegmentedControl"] {
  display: flex;
  justify-content: center;
  margin: .75rem 0 1.4rem;
}
[data-testid="stSegmentedControl"] [role="radiogroup"] {
  display: inline-flex;
  width: auto;
  gap: .42rem;
  padding: .38rem;
  border: 1px solid rgba(91,92,240,.16);
  border-radius: 999px;
  background: rgba(255,255,255,.78);
  box-shadow: 0 8px 22px rgba(73,80,135,.08);
}
[data-testid="stSegmentedControl"] button {
  min-height: 2.85rem;
  padding: .45rem 1.35rem !important;
  border: 1px solid transparent !important;
  border-radius: 999px !important;
  color: #344054 !important;
  background: transparent !important;
  box-shadow: none !important;
  font-weight: 750;
}
[data-testid="stSegmentedControl"] button:hover {
  color: var(--oj-primary-dark) !important;
  background: #f5f3ff !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  border-color: rgba(91,92,240,.22) !important;
  color: #ffffff !important;
  background: linear-gradient(120deg, var(--oj-primary), #7c3aed) !important;
  box-shadow: 0 7px 16px rgba(91,92,240,.22) !important;
}

/* Primary authoring modes: two distinct, substantial choices. */
[class*="problem_authoring_mode"][data-testid="stElementContainer"] {
  width: 100% !important;
}
[class*="problem_authoring_mode"] :is(
  [data-testid="stSegmentedControl"],
  [data-testid="stButtonGroup"]
) {
  display: flex;
  justify-content: center;
  width: 100%;
  margin: .9rem 0 1.8rem;
}
[class*="problem_authoring_mode"] [role="radiogroup"] {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100% !important;
  max-width: 38rem !important;
  gap: .8rem;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
[class*="problem_authoring_mode"] [role="radiogroup"] button {
  gap: .6rem;
  min-height: 4.15rem;
  padding: .8rem 1.45rem !important;
  border: 1px solid rgba(91,92,240,.2) !important;
  border-radius: 18px !important;
  color: #344054 !important;
  background: linear-gradient(145deg, rgba(255,255,255,.98), rgba(245,247,255,.94)) !important;
  box-shadow: 0 8px 20px rgba(73,80,135,.08) !important;
  font-size: 1rem;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
[class*="problem_authoring_mode"] [role="radiogroup"] button::before {
  font-size: 1.35rem;
  line-height: 1;
}
[class*="problem_authoring_mode"] [role="radiogroup"] button:nth-child(1)::before {
  content: "✍️";
}
[class*="problem_authoring_mode"] [role="radiogroup"] button:nth-child(2)::before {
  content: "🤖";
}
[class*="problem_authoring_mode"] [role="radiogroup"] button:hover {
  border-color: rgba(91,92,240,.42) !important;
  background: #f8f7ff !important;
  box-shadow: 0 11px 24px rgba(73,80,135,.13) !important;
  transform: translateY(-2px);
}
[class*="problem_authoring_mode"] [role="radiogroup"] button[aria-pressed="true"],
[class*="problem_authoring_mode"] [role="radiogroup"] button[aria-checked="true"] {
  border-color: transparent !important;
  color: #fff !important;
  background: linear-gradient(120deg, var(--oj-primary), #7c3aed) !important;
  box-shadow: 0 12px 26px rgba(91,92,240,.25) !important;
}

/* AI workflow: numbered stages connected as a lightweight progress path. */
[class*="agent_active_view"][data-testid="stElementContainer"] {
  width: 100% !important;
}
[class*="agent_active_view"] :is(
  [data-testid="stSegmentedControl"],
  [data-testid="stButtonGroup"]
) {
  display: flex;
  justify-content: center;
  width: 100%;
  margin: .75rem 0 1.65rem;
}
[class*="agent_active_view"] [role="radiogroup"] {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  width: 100% !important;
  max-width: 44rem !important;
  gap: 1rem;
  padding: .15rem 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
[class*="agent_active_view"] [role="radiogroup"]::before {
  content: "";
  position: absolute;
  z-index: -1;
  top: 1.5rem;
  left: 15%;
  right: 15%;
  height: 2px;
  background: linear-gradient(90deg, #c7d2fe, #a5f3fc);
}
[class*="agent_active_view"] [role="radiogroup"] button {
  display: flex;
  flex-direction: column;
  gap: .45rem;
  min-height: 4.5rem;
  padding: .25rem .7rem .55rem !important;
  border: 0 !important;
  border-radius: 16px !important;
  color: var(--oj-muted) !important;
  background: transparent !important;
  box-shadow: none !important;
  line-height: 1.25;
}
[class*="agent_active_view"] [role="radiogroup"] button::before {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.55rem;
  height: 2.55rem;
  border: 2px solid #c7d2fe;
  border-radius: 50%;
  color: var(--oj-primary-dark);
  background: #f8faff;
  box-shadow: 0 5px 13px rgba(73,80,135,.1);
  font-size: .88rem;
  font-weight: 850;
}
[class*="agent_active_view"] [role="radiogroup"] button:nth-child(1)::before {
  content: "1";
}
[class*="agent_active_view"] [role="radiogroup"] button:nth-child(2)::before {
  content: "2";
}
[class*="agent_active_view"] [role="radiogroup"] button:nth-child(3)::before {
  content: "3";
}
[class*="agent_active_view"] [role="radiogroup"] button:hover {
  color: var(--oj-primary-dark) !important;
  background: rgba(238,242,255,.72) !important;
}
[class*="agent_active_view"] [role="radiogroup"] button[aria-pressed="true"],
[class*="agent_active_view"] [role="radiogroup"] button[aria-checked="true"] {
  color: var(--oj-primary-dark) !important;
  background: rgba(238,242,255,.82) !important;
  box-shadow: none !important;
}
[class*="agent_active_view"] [role="radiogroup"] button[aria-pressed="true"]::before,
[class*="agent_active_view"] [role="radiogroup"] button[aria-checked="true"]::before {
  border-color: transparent;
  color: #fff;
  background: linear-gradient(135deg, var(--oj-primary), #7c3aed);
  box-shadow: 0 7px 16px rgba(91,92,240,.26);
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 1.4rem;
  padding: .2rem 0;
  border: 0;
  background: transparent;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  padding: .55rem 0;
  border: 0 !important;
  border-radius: 0;
  background: transparent !important;
  box-shadow: none !important;
  font-weight: 750;
}
[data-testid="stTabs"] [aria-selected="true"] {
  color: var(--oj-primary-dark);
  background: transparent !important;
  box-shadow: none !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {
  display: none !important;
}
[data-testid="stMetric"] {
  padding: .9rem 1rem;
  border: 1px solid var(--oj-line);
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 7px 18px rgba(73,80,135,.06);
}
[data-testid="stMetricLabel"] p { color: var(--oj-muted); font-weight: 700; }
[data-testid="stMetricValue"] { color: var(--oj-primary-dark); font-weight: 850; }
[data-testid="stExpander"] {
  border: 1px solid var(--oj-line);
  border-radius: 13px;
  background: rgba(255,255,255,.9);
}
[data-testid="stDataFrame"] {
  overflow: hidden;
  border: 1px solid var(--oj-line);
  border-radius: 14px;
  box-shadow: 0 7px 18px rgba(73,80,135,.06);
}
[data-testid="stDataFrame"] [role="columnheader"] {
  color: #344054;
  background: #eef2ff;
  font-weight: 800;
}
.oj-page-number {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 2.5rem;
  color: var(--oj-muted);
  text-align: center;
  font-size: 1.08rem;
  font-weight: 800;
  white-space: nowrap;
}
[class*="_pagination"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  justify-content: center;
  gap: .35rem;
  width: fit-content;
  max-width: 100%;
  margin: .7rem auto 0;
}
[class*="_pagination"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  flex: 0 0 auto !important;
  width: auto !important;
  min-width: 0 !important;
}
[class*="_pagination"] [data-testid="stButton"],
[class*="_pagination"] [data-testid="stMarkdownContainer"] {
  margin: 0;
}
[class*="_pagination"] [data-testid="stButton"] {
  display: flex;
  justify-content: center;
}
[class*="_pagination"] [data-testid="stButton"] button {
  width: auto !important;
  min-width: 2.5rem !important;
  padding-inline: .72rem !important;
}
[class*="_pagination"] button {
  min-height: 2.5rem;
}
[data-testid="stAlert"] { border-radius: 13px; }
code, pre { font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace !important; }

@keyframes oj-rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes oj-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(249,115,22,.25); }
  50% { box-shadow: 0 0 0 5px rgba(249,115,22,0); }
}

@media (max-width: 900px) {
  .oj-feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  [data-testid="stAppViewContainer"] > .main .block-container { padding: 1.2rem .8rem 3rem; }
  .oj-hero { padding: 1.25rem 1.1rem; border-radius: 17px; }
  .oj-feature-grid { grid-template-columns: 1fr; }
  .oj-hero h1 { font-size: 1.8rem; }
  [data-testid="stHorizontalBlock"] { gap: .55rem; }
  [class*="problem_authoring_mode"] [role="radiogroup"] {
    gap: .5rem;
  }
  [class*="problem_authoring_mode"] [role="radiogroup"] button {
    min-height: 3.55rem;
    padding: .6rem .75rem !important;
  }
  [class*="agent_active_view"] [role="radiogroup"] {
    gap: .25rem;
  }
  [class*="agent_active_view"] [role="radiogroup"]::before {
    display: none;
  }
  [class*="agent_active_view"] [role="radiogroup"] button {
    min-height: 4rem;
    padding-inline: .3rem !important;
    font-size: .78rem;
  }
  [class*="agent_active_view"] [role="radiogroup"] button::before {
    width: 2.15rem;
    height: 2.15rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
/* Fixed light palette, including native widgets and portalled menus. */
:root, .stApp, [data-testid="stAppViewContainer"], [data-baseweb="popover"] {
  color-scheme: light !important;
  --text-color: #172033 !important;
  --background-color: #ffffff !important;
  --secondary-background-color: #f1f4fb !important;
}
[data-testid="stSidebar"], [data-testid="stSidebar"] :is(p, span, a, button),
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"], [data-testid="stExpander"] summary {
  color: var(--oj-ink);
}
[data-testid="stSidebar"] svg { fill: currentColor; color: #52617a; }
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] { border-color: #dfe5f1; }
[data-testid="stSidebar"] button { background: transparent; }
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="textarea"],
[data-baseweb="popover"] > div, [data-baseweb="menu"], [role="listbox"],
[role="dialog"], [data-testid="stExpander"] details {
  background: #fff !important; color: #172033 !important; border-color: #dfe5f1 !important;
}
[data-baseweb="select"] :is(span, input, div), [role="option"],
[data-baseweb="menu"] li, [role="dialog"] :is(label, p, h2),
[data-testid="stExpander"] summary p { color: #172033; }
input, textarea { color: #172033 !important; -webkit-text-fill-color: #172033 !important;
  background-color: #fff !important; caret-color: #2563eb; }
input::placeholder, textarea::placeholder { -webkit-text-fill-color: #8a95a8 !important; }
[data-testid="stCode"] { background: #f6f8fc !important; color: #172033; }
[data-testid="stCode"] pre { background: #f6f8fc !important; }
[data-testid="stCode"] code, [data-testid="stCode"] code span { color: #172033 !important; }
[data-testid="stCode"] .token.keyword { color: #7c3aed !important; }
[data-testid="stCode"] .token:is(.string, .char) { color: #047857 !important; }
[data-testid="stCode"] .token:is(.number, .boolean) { color: #b45309 !important; }
[data-testid="stCode"] .token:is(.function, .class-name) { color: #1d4ed8 !important; }
[data-testid="stCode"] .token.comment { color: #64748b !important; }
[data-testid="stMarkdownContainer"] p, [data-testid="stText"],
[data-testid="stWidgetLabel"] p, [data-baseweb="select"], input, textarea,
[data-testid="stButton"] button p { font-size: 16px; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] :is(p, div) {
  font-size: 36px !important; font-weight: 800 !important;
  line-height: 1.25 !important; color: #4f46d4 !important;
}
[data-testid="stMetricLabel"] p { font-size: 16px !important; font-weight: 650; }
.oj-section-title h2 { font-size: 26px !important; }
[class*="st-key-oj_panel_heading_"] .oj-section-title h2 { font-size: 22px !important; }
.oj-cell-text { font-size: 16px !important; }
[class*="st-key-oj_table_header_"] .oj-cell-text { font-size: 18px !important; font-weight: 750; }
[data-testid="stCaptionContainer"] p, .oj-hero p { font-size: 14px; color: #667085; }
.oj-cell-text--timestamp { white-space: pre-line; font-size: 18px !important; line-height: 1.5; }
.oj-badge--blue { color: #1d4ed8; background: #eff6ff; border-color: #bfdbfe; }
.oj-badge--yellow { color: #854d0e; background: #fef9c3; border-color: #fde047; }
.oj-badge--gray { color: #475569; background: #f1f5f9; border-color: #cbd5e1; }
[class*="problem_authoring_mode"] [role="radiogroup"] button {
  justify-content: center !important; font-size: 28px !important;
}
[class*="problem_authoring_mode"] [role="radiogroup"] button p {
  font-size: 28px !important; font-weight: 750 !important; color: inherit !important;
  white-space: normal !important; overflow: visible !important; line-height: 1.3 !important;
}
[class*="problem_authoring_mode"] [role="radiogroup"] button :is(div, span) {
  white-space: normal !important; text-overflow: clip !important; overflow: visible !important;
}
[class*="problem_authoring_mode"] [role="radiogroup"] button::before { font-size: 34px; }
[class*="problem_authoring_mode"] button[aria-checked="true"] :is(div, span, p),
[data-testid="stBaseButton-primary"] :is(div, span, p) { color: #fff !important; }
[class*="st-key-bank_link_card_"] {
  background: #fff; border: 1px solid #dfe5f1; border-radius: 18px;
  padding: 20px 24px; box-shadow: var(--oj-shadow);
}
[class*="st-key-bank_link_card_"] button p { font-size: 24px !important; font-weight: 750; }
[class*="st-key-oj_panel_body_bank_edit_"] [class*="st-key-oj_panel_toolbar_"] {
  box-shadow: none; border: 0; border-radius: 10px;
}
@media (max-width: 700px) {
  [class*="problem_authoring_mode"] [role="radiogroup"] button p { font-size: 22px !important; }
  [class*="problem_authoring_mode"] [role="radiogroup"] button::before { font-size: 28px; }
  [class*="problem_authoring_mode"] [role="radiogroup"] button { padding: 12px 8px !important; }
  [class*="problem_authoring_mode"] [role="radiogroup"] button {
    flex-direction: column; gap: 8px; min-height: 106px;
  }
}
</style>
"""


def apply_theme() -> None:
    """Inject styles without invoking the Markdown parser on every rerun."""
    st.html(GLOBAL_CSS)
