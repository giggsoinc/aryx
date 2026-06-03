"""Ingest tab — REST / API source. Posts a job to the backend for ingestion."""
from __future__ import annotations

import json

import streamlit as st

from aryx.ui import api, ingest_client


def render(workspace_context: str = "") -> None:
    """REST API form: URL + auth + record path + pagination → ingest job."""
    if workspace_context.strip():
        st.markdown(
            f'<div class="aryx-ws-summary">📝 <b>Workspace context:</b> '
            f'<i>{workspace_context}</i></div>',
            unsafe_allow_html=True,
        )
    st.markdown("**REST API endpoint** — Aryx will fetch JSON and treat each "
                "object as one record.")
    url = st.text_input("URL",
                        placeholder="https://api.example.com/v1/customers")
    auth_kind = st.selectbox("Auth", ["None", "Bearer", "API-Key header"])
    auth_value = ""
    api_key_name = "X-API-Key"
    if auth_kind == "Bearer":
        auth_value = st.text_input("Bearer token", type="password")
    elif auth_kind == "API-Key header":
        api_key_name = st.text_input("Header name", value="X-API-Key")
        auth_value = st.text_input("API key", type="password")
    record_path = st.text_input(
        "Records JSON path (dotted; empty = top-level list)",
        placeholder="data.items",
    )
    col1, col2 = st.columns(2)
    page_param = col1.text_input("Pagination query param (optional)",
                                 placeholder="page_token")
    next_path = col2.text_input("Next-page JSON path (optional)",
                                placeholder="next_page")
    headers: dict[str, str] = {}
    if auth_kind == "Bearer" and auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"
    elif auth_kind == "API-Key header" and auth_value:
        headers[api_key_name] = auth_value
    st.caption("Connect & ingest will run a discovery job (entities are "
               "auto-typed) using your workspace's business context.")
    if st.button("Preview fetch", type="primary",
                 disabled=not url.strip()):
        try:
            payload = {
                "workspace_id": api.current_workspace(),
                "url": url, "headers": headers,
                "record_path": record_path,
                "page_param": page_param, "next_page_path": next_path,
                "context": workspace_context,
            }
            resp = ingest_client.api._post("/ingest/rest/preview", payload,
                                           timeout=60)
            st.success(f"Fetched {resp.get('count', 0)} record(s).")
            st.info(resp.get("message", ""))
            if resp.get("sample"):
                st.json(resp["sample"])
        except Exception as exc:
            st.error(f"Fetch failed: {exc}")
    with st.expander("Preview the request"):
        st.code(json.dumps({"url": url, "headers": headers,
                            "record_path": record_path}, indent=2),
                language="json")
