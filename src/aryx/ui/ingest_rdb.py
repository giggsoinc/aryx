"""Database source — connect to any RDBMS, let the agent auto-discover tables."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api

_DIALECTS = ["postgresql", "mysql", "mariadb", "oracle", "sqlite"]


def _connect_form() -> None:
    with st.form("db_connect"):
        col1, col2, col3 = st.columns([2, 2, 1])
        dialect = col1.selectbox("RDBMS", _DIALECTS)
        host = col2.text_input("Host", placeholder="db.example.com")
        port = col3.text_input("Port", placeholder="5432")
        database = st.text_input("Database", placeholder="sales")
        col4, col5 = st.columns(2)
        user = col4.text_input("User")
        password = col5.text_input("Password", type="password")
        connect = st.form_submit_button("Connect & introspect", type="primary")
    if connect:
        try:
            res = api.db_connect({"dialect": dialect, "host": host, "port": port,
                                  "database": database, "user": user, "password": password})
            st.session_state.rdb_conn = res["connection_id"]
            st.session_state.rdb_tables = res.get("tables", [])
            st.session_state.pop("rdb_disc", None)
            st.success(f"Connected — found {len(res.get('tables', []))} tables.")
        except Exception as exc:
            st.error(f"Connection failed: {exc}")


def _discover(context: str) -> None:
    if not context.strip():
        st.warning("Describe what you're building in the context box above first.")
        return
    if st.button("🤖 Run discovery agent"):
        with st.spinner("Agent reading the schema against your context…"):
            try:
                st.session_state.rdb_disc = api.db_discover(st.session_state.rdb_conn, context)
            except Exception as exc:
                st.error(f"Discovery failed: {exc}")


def _review_and_ingest() -> None:
    disc = st.session_state.get("rdb_disc")
    if not disc:
        return
    st.markdown("**The agent proposes these entities** (edit or untick any):")
    chosen: list[dict] = []
    for t in disc.get("tables", []):
        c1, c2, c3 = st.columns([2, 2, 3])
        inc = c1.checkbox(t["table"], value=True, key=f"inc_{t['table']}")
        otype = c2.text_input("type", t["ontology_type"], key=f"ot_{t['table']}",
                              label_visibility="collapsed")
        keys = c3.text_input("keys", ",".join(t.get("match_keys", [])),
                             key=f"mk_{t['table']}", label_visibility="collapsed")
        if inc:
            chosen.append({"table": t["table"], "ontology_type": otype,
                           "match_keys": [k.strip() for k in keys.split(",") if k.strip()]})
    edges = disc.get("edges", [])
    if edges:
        rels = ", ".join(f"{e['source_type']}→{e['target_type']} ({e['name']})" for e in edges[:6])
        st.caption(f"Relationships found: {rels}")
    if st.button("Ingest selected tables", type="primary") and chosen:
        try:
            resp = api.ingest_multi(st.session_state.rdb_conn, chosen, edges)
            st.session_state.active_job = resp.get("job_id")
        except Exception as exc:
            st.error(f"Ingest failed: {exc}")


def render(context: str) -> None:
    st.markdown("##### 1 · Connect")
    _connect_form()
    if st.session_state.get("rdb_conn"):
        st.markdown("##### 2 · Auto-discover")
        _discover(context)
        st.markdown("##### 3 · Review & ingest")
        _review_and_ingest()
