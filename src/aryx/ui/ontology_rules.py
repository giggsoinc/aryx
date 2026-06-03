"""Ontology page → Rules tab: define inference rules + run the evaluator.

Closes the deck's Slide 5/8 inference claim. Each rule is a tiny JSON DSL
that the backend evaluator turns into FalkorDB labels + INF_ edges.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import api_ext

_OPS = [">", ">=", "<", "<=", "==", "!=", "contains"]
_ACTIONS = ["set_label", "add_relationship"]


def _rule_form() -> None:
    """Form to create or update one rule."""
    with st.form("rule_form", clear_on_submit=True):
        st.markdown("**Add or update a rule**")
        name = st.text_input("Rule name", placeholder="platinum_customer")
        c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
        when_type = c1.text_input("When type", placeholder="Customer")
        when_attr = c2.text_input("Attribute", placeholder="revenue")
        when_op = c3.selectbox("Operator", _OPS, index=0)
        when_val = c4.text_input("Value", placeholder="1000000")
        action = st.selectbox("Action", _ACTIONS, index=0)
        col_a, col_b = st.columns(2)
        label = col_a.text_input("Set label / rel name", placeholder="Platinum")
        target = col_b.text_input("Target entity name (if add_relationship)",
                                  placeholder="Platinum")
        target_type = st.text_input("Target type (if add_relationship)",
                                    placeholder="Tier")
        enabled = st.checkbox("Enabled", value=True)
        submitted = st.form_submit_button("Save rule", type="primary")
    if not submitted or not name or not when_type or not when_attr:
        return
    when = {"type": when_type, "attr": when_attr, "op": when_op,
            "value": when_val}
    if action == "set_label":
        then: dict = {"set_label": label or name.title()}
    else:
        then = {"add_relationship": label or name.upper(),
                "target_type": target_type, "target_name": target}
    try:
        api_ext.upsert_rule(name, when, then, enabled=enabled)
        st.success(f"Saved rule '{name}'.")
        st.rerun()
    except Exception as exc:
        st.error(f"Save failed: {exc}")


def _rules_table(rules: list[dict]) -> None:
    """Render the live rules table with toggle + delete buttons."""
    if not rules:
        st.info("No rules yet. Add one above to start inferring facts.")
        return
    st.markdown("**Active rules**")
    for r in rules:
        cols = st.columns([3, 4, 1, 1])
        cols[0].markdown(f"**{r['name']}** · fires {r.get('fires_count', 0)}")
        cols[1].caption(f"if {r['when'].get('type')}.{r['when'].get('attr')} "
                        f"{r['when'].get('op')} {r['when'].get('value')} "
                        f"→ {r['then']}")
        if cols[2].button("Toggle", key=f"tog_{r['name']}"):
            try:
                api_ext.upsert_rule(r["name"], r["when"], r["then"],
                                    enabled=not r["enabled"])
                st.rerun()
            except Exception as exc:
                st.error(f"Toggle failed: {exc}")
        if cols[3].button("🗑", key=f"del_{r['name']}"):
            try:
                api_ext.delete_rule(r["name"])
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")


def render() -> None:
    """Render the Rules tab content."""
    st.markdown("Rules let Aryx infer facts that aren't stored — e.g. "
                "*Customers with revenue > $1M are Platinum*. Inferred "
                "edges and labels appear on the Graph with a dashed style.")
    try:
        rules = api_ext.list_rules()
    except Exception as exc:
        st.error(f"Cannot load rules: {exc}")
        rules = []
    _rules_table(rules)
    st.divider()
    _rule_form()
    st.divider()
    if st.button("▶ Run evaluator now", type="primary"):
        try:
            res = api_ext.evaluate_rules()
            st.success(
                f"Evaluator ran. {res.get('rules_evaluated', 0)} rule(s) "
                f"checked · {res.get('total_fires', 0)} inferences written. "
                "Open the Graph tab to see them."
            )
            st.json(res.get("per_rule") or {})
        except Exception as exc:
            st.error(f"Evaluator failed: {exc}")
