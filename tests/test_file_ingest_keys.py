from __future__ import annotations

from aryx.api.file_ingest_api import _columns_in_context


def test_columns_in_context_requires_identity_clause() -> None:
    context = (
        "Analyze orders, customers, and email reachability. "
        "Include order_id for traceability."
    )
    cols = ["order_id", "customer_id", "email"]

    assert _columns_in_context(context, cols) == []


def test_columns_in_context_honors_explicit_identity_clause() -> None:
    context = (
        "A parent is identified by parent_key. "
        "Each child is uniquely identified by parent_key and child_key."
    )
    cols = ["child_key", "parent_key", "email"]

    assert _columns_in_context(context, cols) == ["parent_key", "child_key"]
