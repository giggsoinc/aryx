"""Approved operation and visualization catalogues for planning (C07).

These are the governed, versioned vocabularies of analytical operations and
chart types a plan is permitted to use. A missing catalogue is a hard stop
(control gate). Kept in code for now (like the C01 chart catalogue); can move to
a DB-backed governance table later.
"""
from __future__ import annotations

CATALOGUE_VERSION = "1.0"

OPERATIONS: list[str] = [
    "count",
    "distinct_count",
    "sum",
    "average",
    "median",
    "group_by",
    "filter",
    "sort",
    "top_n",
    "percentage",
    "ratio",
]

CHARTS: list[str] = [
    "kpi_card",
    "bar",
    "line",
    "scatter",
    "donut",
    "table",
]
