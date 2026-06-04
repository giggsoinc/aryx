"""Global CSS injection — Aryx brand, light-mode LOCKED.

Pins the page to a single colour scheme so the UI never flickers between
day and night, even when the host browser advertises a dark preference.
Three layers of lock are applied:
  1. <meta name="color-scheme" content="light"> tells the user agent
     "do not even consider dark mode" — eliminates the FOUC.
  2. CSS `color-scheme: only light` on :root for the same reason at the
     CSS layer (defensive — covers older Safari).
  3. An overriding @media (prefers-color-scheme: dark) ruleset that
     re-pins every brand colour to its light value — so even when a
     downstream component injects `[data-theme="dark"]` we win.
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<meta name="color-scheme" content="light">
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;700;800&display=swap');

:root {
  color-scheme: only light !important;
  --aryx-primary:   #1E3A8A;
  --aryx-primary-2: #0D1B5A;
  --aryx-accent:    #2D7DFF;
  --aryx-accent-2:  #3FB6FF;
  --aryx-ink:       #0B1430;
  --aryx-paper:     #FFFFFF;
  --aryx-paper-2:   #F4F6FB;
  --aryx-muted:     #6B7280;
  /* Pin Streamlit's own theme tokens so internal components stop
     consulting prefers-color-scheme. */
  --background-color: #FFFFFF !important;
  --secondary-background-color: #F4F6FB !important;
  --text-color: #0B1430 !important;
  --primary-color: #2D7DFF !important;
}

html, body { background: #FFFFFF !important; color: #0B1430 !important;
  color-scheme: only light !important;
  font-family: 'Montserrat', 'Inter', -apple-system, sans-serif !important;
  font-size: 18px; }

.block-container { padding-top: 2.0rem; max-width: 1320px; }

p, li, .stMarkdown { font-size: 1.05rem !important; line-height: 1.55; }

h1 { font-size: 3.0rem !important; font-weight: 800 !important;
     letter-spacing: -0.02em; color: var(--aryx-primary-2) !important; }
h2 { font-size: 2.1rem !important; font-weight: 700 !important;
     color: var(--aryx-primary) !important; }
h3 { font-size: 1.55rem !important; font-weight: 600 !important;
     color: var(--aryx-ink) !important; }

[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="block-container"] {
  background: #FFFFFF !important; color: #0B1430 !important; }

section[data-testid="stSidebar"] { min-width: 300px;
  background: linear-gradient(180deg, #F4F6FB 0%, #E7ECF7 100%) !important;
  color: #0B1430 !important; }
section[data-testid="stSidebar"] * { color: #0B1430 !important; }
section[data-testid="stSidebar"] h1 { font-size: 1.8rem !important;
  color: #0D1B5A !important; }

label, .stRadio label p { font-size: 1.1rem !important; font-weight: 500;
  color: #0B1430 !important; }
.stRadio [role="radiogroup"] label { padding: 0.45rem 0; }

div[data-testid="stMetricValue"] { font-size: 2.3rem !important;
  color: var(--aryx-primary) !important; }
div[data-testid="stMetricLabel"] { font-size: 1.0rem !important;
  color: #0B1430 !important; }

.stButton button { font-size: 1.1rem; font-weight: 600;
  padding: 0.6rem 1.6rem; border-radius: 8px; }
.stTextInput input, .stTextArea textarea {
  font-size: 1.05rem !important;
  background: #FFFFFF !important; color: #0B1430 !important; }

.aryx-step { background: var(--aryx-paper-2); border: 1px solid #D9DEEB;
  border-radius: 12px; padding: 1.1rem 1.3rem; margin-bottom: 0.8rem;
  color: #0B1430 !important; }
.aryx-step .num { display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 50%; background: var(--aryx-accent);
  color: #fff; font-weight: 700; margin-right: 0.7rem; }
.aryx-hero { font-size: 1.2rem; line-height: 1.65; color: var(--aryx-ink); }

.aryx-brandbar { background: linear-gradient(135deg, var(--aryx-primary-2) 0%,
  var(--aryx-primary) 60%, var(--aryx-accent) 100%); color: #fff;
  padding: 1.4rem 1.8rem; border-radius: 14px; margin-bottom: 1.2rem; }
.aryx-brandbar h1 { color: #fff !important; margin: 0 !important;
  font-weight: 800 !important; letter-spacing: 0.04em; }
.aryx-brandbar .tag { display: block; font-size: 0.75rem; font-weight: 500;
  letter-spacing: 0.22em; text-transform: uppercase;
  color: var(--aryx-accent-2); margin-top: 0.2rem; }

.aryx-ws-summary { background: var(--aryx-paper-2);
  border-left: 4px solid var(--aryx-accent);
  padding: 0.7rem 1.1rem; border-radius: 6px; margin-bottom: 1.1rem;
  font-size: 0.92rem; color: var(--aryx-ink) !important; }
.aryx-ws-summary b { color: var(--aryx-primary); }
.aryx-ws-summary .muted { color: var(--aryx-muted); font-size: 0.85rem; }

.aryx-sidebar-mark { text-align: center; padding: 0.5rem 0 0.2rem 0; }
.aryx-sidebar-mark .word { font-size: 1.9rem; font-weight: 800;
  letter-spacing: 0.18em; color: var(--aryx-primary-2); }
.aryx-sidebar-mark .tagline { font-size: 0.62rem; font-weight: 500;
  letter-spacing: 0.18em; text-transform: uppercase; color: var(--aryx-accent); }

/* Defensive: even if a dark media query somehow fires, re-pin everything. */
@media (prefers-color-scheme: dark) {
  html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background: #FFFFFF !important; color: #0B1430 !important; }
  section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #F4F6FB 0%, #E7ECF7 100%) !important; }
  section[data-testid="stSidebar"] * { color: #0B1430 !important; }
}
</style>
"""


def inject() -> None:
    """Apply the Aryx visual theme (light-locked) to the current page."""
    st.markdown(_CSS, unsafe_allow_html=True)
