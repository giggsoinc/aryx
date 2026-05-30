"""Global CSS injection — larger fonts, balanced spacing, polished dark theme."""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
:root { --aryx-accent: #4A90E2; --aryx-accent2: #E8775A; }

html, body, [class*="css"] { font-size: 17px; }

.block-container { padding-top: 2.2rem; max-width: 1280px; }

h1 { font-size: 2.6rem !important; font-weight: 800 !important; letter-spacing: -0.02em; }
h2 { font-size: 1.9rem !important; font-weight: 700 !important; }
h3 { font-size: 1.4rem !important; font-weight: 600 !important; }

section[data-testid="stSidebar"] { min-width: 270px; }
section[data-testid="stSidebar"] h1 { font-size: 1.8rem !important; }

label, .stRadio label p { font-size: 1.05rem !important; font-weight: 500; }

.stRadio [role="radiogroup"] label { padding: 0.35rem 0; }

div[data-testid="stMetricValue"] { font-size: 2.1rem !important; }

.stButton button { font-size: 1.05rem; font-weight: 600; padding: 0.5rem 1.4rem; border-radius: 8px; }

.aryx-step { background: #1c2230; border: 1px solid #2c3444; border-radius: 12px;
  padding: 1.1rem 1.3rem; margin-bottom: 0.8rem; }
.aryx-step .num { display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 50%; background: var(--aryx-accent);
  color: #fff; font-weight: 700; margin-right: 0.7rem; }
.aryx-hero { font-size: 1.25rem; line-height: 1.65; color: #c8d0dc; }
</style>
"""


def inject() -> None:
    """Apply the Aryx visual theme to the current page."""
    st.markdown(_CSS, unsafe_allow_html=True)
