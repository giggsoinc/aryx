"""UI catalogues — the deterministic allowlists C01 validates preferences against.

LLM policy: No. These are versioned, hand-curated vocabularies. A preference
value outside its catalogue is never dropped and never blocks the request — it
is retained and surfaced as a warning (fallback: retain unsupported preference
as a warning). KPIs and dimensions are intentionally NOT catalogued: they are
domain-specific and open-ended, so allowlisting them would flag legitimate terms.

All entries are lowercase; membership checks lowercase the candidate first.
"""
from __future__ import annotations

CATALOGUE_VERSION = "1.0"

CHART_TYPES: frozenset[str] = frozenset({
    "bar",
    "column",
    "line",
    "area",
    "pie",
    "donut",
    "scatter",
    "bubble",
    "heatmap",
    "table",
    "kpi",
    "funnel",
    "map",
})

AUDIENCES: frozenset[str] = frozenset({
    "executive",
    "sales leadership",
    "finance",
    "operations",
    "marketing",
    "product",
    "engineering",
    "customer success",
    "general",
})
