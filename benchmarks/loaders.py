"""Dataset loading + conversion to aryx ResolutionRecord objects."""
from __future__ import annotations

from aryx.models import ResolutionRecord
from aryx.resolution.classical import normalize


def load_dataset(name: str) -> tuple[dict[str, dict], set[frozenset]]:
    """Load a named benchmark dataset.

    Args:
        name: febrl1-4 or mfg.

    Returns:
        (records_dict, true_pairs_set)
    """
    if name.startswith("febrl"):
        n = int(name[5:]) if len(name) > 5 else 1
        from benchmarks.datasets.fetch import load_febrl
        return load_febrl(n)
    if name == "mfg":
        from benchmarks.datasets.make_mfg import load_mfg
        return load_mfg()
    raise ValueError(f"Unknown dataset '{name}'. Use: febrl1-4, mfg")


def to_resolution_records(records: dict[str, dict]) -> list[ResolutionRecord]:
    """Convert str-keyed field dicts to ResolutionRecord objects."""
    out = []
    for idx, (str_id, fields) in enumerate(records.items()):
        text = " ".join(str(v) for v in fields.values() if v and str(v).strip())
        out.append(ResolutionRecord(
            record_id=idx,
            text=normalize(text),
            payload={**fields, "__str_id": str_id},
        ))
    return out


def int_to_str_map(recs: list[ResolutionRecord]) -> dict[int, str]:
    """Map internal int record ids back to the dataset's string ids."""
    return {r.record_id: r.payload["__str_id"] for r in recs}
