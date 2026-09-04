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
  animation: oj-rise .35s ease-out both;
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

[class*="problem_catalog"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  min-height: 2.35rem;
  padding: .1rem .7rem;
  border-bottom: 1px solid var(--oj-line);
}
[class*="problem_catalog"][data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="problem_catalog"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="problem_catalog"] [data-testid="stButton"] button {
  min-height: auto;
  padding: .15rem 0;
  border: 0;
  background: transparent;
  color: var(--oj-primary);
  box-shadow: none;
  font-weight: 750;
  text-align: left;
}
[class*="problem_catalog"] [data-testid="stButton"] button:hover {
  color: var(--oj-primary-dark);
  background: transparent;
  box-shadow: none;
  text-decoration: underline;
  transform: none;
}
[class*="problem_catalog"] [data-testid="stButton"] button:focus-visible {
  outline: 3px solid rgba(91,92,240,.25);
  outline-offset: 3px;
}
[class*="problem_catalog"] .oj-badges {
  margin: 0;
  transform: translateY(-.45rem);
}

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
[class*="submission_catalog"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  min-height: 2.35rem;
  padding: .1rem .65rem;
  border-bottom: 1px solid var(--oj-line);
}
[class*="submission_catalog"][data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="submission_catalog"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="submission_catalog"] [data-testid="stButton"] button {
  min-height: auto;
  padding: .12rem 0;
  border: 0;
  background: transparent;
  color: #2563eb;
  box-shadow: none;
  font-size: 1.22rem;
  font-weight: 850;
  line-height: 2rem;
}
[class*="submission_catalog"] [data-testid="stButton"] button p {
  margin: 0;
  color: inherit;
  font-size: 1.22rem !important;
  font-weight: 850 !important;
  line-height: 2rem !important;
}
[class*="submission_catalog"] [data-testid="stButton"] button:hover {
  color: #1d4ed8;
  background: transparent;
  box-shadow: none;
  text-decoration: underline;
  transform: none;
}
[class*="submission_catalog"] .oj-badges {
  margin: 0;
  transform: translateY(-.45rem);
}
[class*="submission_catalog"] [data-testid="stColumn"] > div { width: 100%; }
.oj-submission-id,
.oj-result-number {
  font-size: 1.22rem;
  font-weight: 850;
  line-height: 2rem;
  transform: translateY(-.45rem);
}
.oj-result-number--success { color: var(--oj-success); }
.oj-result-number--failure { color: var(--oj-danger); }
[class*="testcase_results"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  min-height: 2.35rem;
  padding: .1rem .7rem;
  border-bottom: 1px solid var(--oj-line);
}
[class*="testcase_results"][data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="testcase_results"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="testcase_results"] .oj-badges {
  margin: 0;
  transform: translateY(-.45rem);
}
[class*="testcase_results"] [data-testid="stColumn"] > div { width: 100%; }

[class*="user_catalog"] {
  overflow: hidden;
  border: 1px solid var(--oj-line);
  border-radius: 14px;
  background: rgba(255,255,255,.72);
  box-shadow: 0 7px 18px rgba(73,80,135,.06);
}
[class*="user_catalog"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  min-height: 2.35rem;
  padding: .1rem .7rem;
  border-bottom: 1px solid var(--oj-line);
}
[class*="user_catalog"][data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="user_catalog"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="user_catalog_header"] [data-testid="stHorizontalBlock"] {
  background: rgba(238,242,255,.82);
}
[class*="user_catalog"] [data-testid="stColumn"] > div { width: 100%; }
[class*="user_catalog"] .oj-badges {
  margin: 0;
  transform: translateY(-.45rem);
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
</style>
"""


def apply_theme() -> None:
    """Inject styles without invoking the Markdown parser on every rerun."""
    st.html(GLOBAL_CSS)
