"""Fetch/load benchmark datasets for ER evaluation.

Febrl 1-4 are loaded from the recordlinkage package (no network required).
Install: pip install recordlinkage

Returns a standardized (records_dict, true_pairs_set) tuple where:
  records_dict: {str_id: dict_of_fields}
  true_pairs_set: set of frozenset({id_a, id_b})
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _df_to_records(df) -> dict[str, dict]:
    """Convert a Febrl DataFrame to {rec_id: field_dict}."""
    out = {}
    for idx, row in df.iterrows():
        out[str(idx)] = {k: ("" if v != v else str(v)) for k, v in row.items()}
    return out


def _links_to_pairs(links) -> set[frozenset]:
    """Convert a MultiIndex of true links to a set of frozenset pairs."""
    return {frozenset([str(a), str(b)]) for a, b in links}


def load_febrl(n: int = 1) -> tuple[dict[str, dict], set[frozenset]]:
    """Load Febrl dataset n (1-4) from recordlinkage.

    Args:
        n: Dataset number 1-4.

    Returns:
        (records, true_pairs)
    """
    try:
        from recordlinkage.datasets import load_febrl1, load_febrl2, load_febrl3, load_febrl4
    except ImportError as exc:
        raise ImportError("pip install recordlinkage~=0.14") from exc

    loaders = {1: load_febrl1, 2: load_febrl2, 3: load_febrl3, 4: load_febrl4}
    if n not in loaders:
        raise ValueError(f"febrl n must be 1-4, got {n}")

    df, links = loaders[n](return_links=True)
    records = _df_to_records(df)
    pairs = _links_to_pairs(links)
    logger.info("febrl%d: %d records, %d true pairs", n, len(records), len(pairs))
    return records, pairs


def record_text(fields: dict[str, str], keys: list[str] | None = None) -> str:
    """Build the match-text string for a Febrl record.

    Febrl records have given_name, surname as the primary match keys.
    Falling back to all fields when keys not specified.
    """
    if keys is None:
        keys = ["given_name", "surname", "street_number", "address_1", "suburb"]
    parts = [fields.get(k, "") for k in keys]
    return " ".join(p for p in parts if p)
