"""Settings → MCP Server section: status + copy-paste configs for agents."""
from __future__ import annotations

import os

import streamlit as st


def _endpoint() -> str:
    base = os.environ.get(
        "ARYX_PUBLIC_URL",
        os.environ.get("ARYX_API_URL", "http://localhost:8088"),
    )
    return base.rstrip("/")


_DESKTOP_JSON = (
    '{\n  "mcpServers": {\n    "aryx": {\n'
    '      "url": "{base}/mcp"\n    }\n  }\n}'
)

_STDIO_JSON = (
    '{\n  "mcpServers": {\n    "aryx": {\n'
    '      "command": "python",\n'
    '      "args": ["-m", "aryx.mcp"],\n'
    '      "env": {"ARYX_API_URL": "{base}"}\n'
    '    }\n  }\n}'
)


def render() -> None:
    """Render the Settings MCP section: endpoint, tools, copy-paste configs."""
    base = _endpoint()
    st.subheader("MCP Server (Claude, Cursor, Continue, any agent)")
    st.caption(
        "Aryx exposes 4 read-only tools over MCP: `search_entities`, "
        "`get_entity`, `get_neighbors`, `get_provenance`. External agents "
        "can query the graph without changing anything in your data."
    )
    st.markdown(
        f"**Endpoint** · `{base}/mcp` &nbsp;·&nbsp; "
        "🔒 read-only &nbsp;·&nbsp; 🔓 no-auth (demo)"
    )
    tab_desk, tab_code, tab_cursor, tab_stdio = st.tabs(
        ["Claude Desktop", "Claude Code", "Cursor / Continue", "Local (stdio)"]
    )
    with tab_desk:
        st.code(_DESKTOP_JSON.replace("{base}", base), language="json")
        st.caption(
            "Save to `~/Library/Application Support/Claude/"
            "claude_desktop_config.json` and restart Claude Desktop."
        )
    with tab_code:
        st.code(f"claude mcp add aryx --transport sse --url {base}/mcp",
                language="bash")
    with tab_cursor:
        st.code(_DESKTOP_JSON.replace("{base}", base), language="json")
        st.caption(
            "Cursor: `~/.cursor/mcp.json` · "
            "Continue: `~/.continue/config.json` (mcpServers section)."
        )
    with tab_stdio:
        st.code(_STDIO_JSON.replace("{base}", base), language="json")
        st.caption(
            "Use stdio when running Aryx locally and Claude Desktop is on "
            "the same machine."
        )
