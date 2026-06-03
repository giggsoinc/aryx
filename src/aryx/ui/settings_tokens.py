"""Settings → MCP Tokens section: issue / list / revoke bearer tokens."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api_ext


def _new_token_form() -> None:
    """Form to issue a new token. Shows the raw token ONCE."""
    label = st.text_input("Label for the new token",
                          placeholder="e.g. claude-desktop-rajiv",
                          key="mcp_tok_label")
    if st.button("Generate token", type="primary", key="mcp_tok_gen"):
        try:
            row = api_ext.issue_mcp_token(label or "unnamed")
        except Exception as exc:
            st.error(f"Issue failed: {exc}")
            return
        st.success("Token created. **Copy it now — it will not be shown again.**")
        st.code(row.get("token", ""), language="text")
        st.caption(f"Prefix: `{row.get('prefix')}` · "
                   f"Issued at {row.get('created_at')}")


def _token_table(tokens: list[dict]) -> None:
    """List existing tokens with revoke buttons."""
    if not tokens:
        st.info("No tokens yet. Issue one above so external MCP clients can "
                "connect to /mcp.")
        return
    for t in tokens:
        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown(f"**{t.get('label') or 'unnamed'}**")
        cols[1].caption(f"prefix `{t.get('prefix')}`")
        if t.get("revoked_at"):
            cols[2].caption(f"🚫 revoked {t.get('revoked_at')}")
        elif t.get("last_used_at"):
            cols[2].caption(f"last used {t.get('last_used_at')}")
        else:
            cols[2].caption("never used")
        if not t.get("revoked_at") and cols[3].button(
            "🗑", key=f"rev_{t.get('id')}"
        ):
            try:
                api_ext.revoke_mcp_token(int(t.get("id", 0)))
                st.rerun()
            except Exception as exc:
                st.error(f"Revoke failed: {exc}")


def render() -> None:
    """Settings → Bearer tokens section."""
    st.subheader("MCP bearer tokens")
    st.caption("Issue a token per agent. Aryx hashes and stores only the "
               "prefix — the plain token is shown once at creation.")
    try:
        tokens = api_ext.list_mcp_tokens()
    except Exception as exc:
        st.error(f"Cannot load tokens: {exc}")
        tokens = []
    _token_table(tokens)
    st.divider()
    _new_token_form()
