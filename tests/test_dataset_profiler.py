"""Tests for the Deterministic Dataset Profiler (C03) — pure, no DB."""
from __future__ import annotations

import math

from aryx.profiler import profile_dataset

CSV = (
    b"contract_id,region,contract_value,renewal_status\n"
    b"C001,North,1000,Renewed\n"
    b"C002,South,,Pending\n"
    b"C003,East,1500,Not Renewed\n"
    b"C004,West,2000,Renewed\n"
    b"C005,North,2500,Pending\n"
)


def _profile():
    return profile_dataset(CSV, "csv", "dataset_contracts", "v1")


def _col(p, name):
    return next(c for c in p.columns if c.name == name)


def test_shape_and_id() -> None:
    p = _profile()
    assert p.dataset_profile_id == "profile_dataset_contracts_v1"
    assert p.row_count == 5
    assert p.column_count == 4
    assert p.profile_status == "valid"


def test_identifier_column() -> None:
    c = _col(_profile(), "contract_id")
    assert c.canonical_type == "identifier"
    assert c.candidate_role == "identifier"
    assert c.unique_count == 5
    assert c.null_count == 0


def test_categorical_dimension() -> None:
    c = _col(_profile(), "region")
    assert c.canonical_type == "categorical"
    assert c.candidate_role == "dimension"
    assert set(c.sample_values) <= {"North", "South", "East", "West"}
    assert c.top_categories  # frequencies computed


def test_numeric_measure_with_nulls() -> None:
    c = _col(_profile(), "contract_value")
    assert c.canonical_type == "numeric"
    assert c.candidate_role == "measure"
    assert c.null_count == 1
    assert c.min == 1000.0 and c.max == 2500.0
    assert c.mean is not None and c.median is not None


def test_status_role_detected() -> None:
    c = _col(_profile(), "renewal_status")
    # Name ends in 'status' and values are in the status vocab.
    assert c.candidate_role == "status"


def test_high_cardinality_text_with_real_repeats_is_still_a_dimension() -> None:
    # Regression: a column like "account_name_clean" or "end_quarter" can
    # easily exceed the _CATEGORICAL_MAX distinct-value cutoff (e.g. 60
    # fiscal quarters, or hundreds of real account names) while still being
    # a perfectly legitimate group-by/top-N dimension — every value repeats
    # across many rows. Before this fix such a column fell all the way
    # through to canonical_type "text" and role "attribute", making it
    # invisible to dashboard planning even though nothing about it is
    # actually high-cardinality free text.
    rows = [f"account_{i % 80}" for i in range(400)]  # 80 distinct, 5x repeat each
    csv = b"id,account_name_clean\n" + b"".join(
        f"{i},{rows[i]}\n".encode() for i in range(400)
    )
    p = profile_dataset(csv, "csv", "dataset_contracts", "v1")
    c = _col(p, "account_name_clean")
    assert c.canonical_type == "text"  # still too many distinct values for "categorical"
    assert c.candidate_role == "dimension"  # but real repetition makes it groupable
    assert c.unique_count == 80


def test_near_unique_free_text_stays_an_unapproved_attribute() -> None:
    # Contrast case: genuinely high-cardinality free text (a comments/notes
    # field where almost every value is distinct) must NOT be promoted to
    # "dimension" — grouping by it would produce ~one bucket per row.
    rows = [f"note about ticket {i} needs review" for i in range(200)]
    csv = b"id,notes\n" + b"".join(f"{i},{rows[i]}\n".encode() for i in range(200))
    p = profile_dataset(csv, "csv", "dataset_contracts", "v1")
    c = _col(p, "notes")
    assert c.canonical_type == "text"
    assert c.candidate_role == "attribute"


def test_quality_flag_missing_values() -> None:
    p = _profile()
    flags = [f for f in p.quality_flags if f.column == "contract_value"]
    assert any(f.code == "missing_values" and f.count == 1 for f in flags)


def test_constant_column_flagged() -> None:
    data = b"a,b\n1,x\n2,x\n3,x\n"
    p = profile_dataset(data, "csv", "ds", "v1")
    b = _col(p, "b")
    assert any(f.code == "constant" for f in p.quality_flags if f.column == "b")
    assert b.canonical_type in ("categorical", "text")


def test_json_flattening_and_roles() -> None:
    data = b'[{"id": 1, "geo": {"country": "US"}, "amt": 10.5}, {"id": 2, "geo": {"country": "IN"}, "amt": 20.0}]'
    p = profile_dataset(data, "json", "ds_json", "v1")
    names = {c.name for c in p.columns}
    assert "geo.country" in names
    assert _col(p, "id").candidate_role == "identifier"
    assert _col(p, "amt").candidate_role == "measure"
    assert any("flattened" in lim for lim in p.limitations)


def test_bom_prefixed_json_profiles_without_crashing() -> None:
    # dataset/formats.py accepts BOM-prefixed JSON at ingest (utf-8-sig); the
    # profiler must decode the same way or a legitimately-accepted file 500s
    # here instead of profiling.
    data = b'\xef\xbb\xbf[{"id": 1, "amt": 10.5}, {"id": 2, "amt": 20.0}]'
    p = profile_dataset(data, "json", "ds_bom", "v1")
    assert p.row_count == 2
    assert p.profile_status == "valid"


def test_duplicate_rows_counted() -> None:
    data = b"a,b\n1,x\n1,x\n2,y\n"
    p = profile_dataset(data, "csv", "ds", "v1")
    assert p.duplicate_row_count == 1


def test_non_finite_values_do_not_crash_or_poison_stats() -> None:
    # 'NaN'/'Infinity'/'1_000' must NOT be treated as numbers — otherwise
    # non-finite stats break Postgres jsonb serialization (C03 crash fix).
    import json
    data = b"amount\n100\nNaN\nInfinity\n1_000\n200\n"
    p = profile_dataset(data, "csv", "ds", "v1")
    col = next(c for c in p.columns if c.name == "amount")
    # Mixed numeric + non-numeric strings -> not a clean numeric column.
    assert col.canonical_type != "numeric"
    for stat in (col.min, col.max, col.mean, col.median):
        assert stat is None or math.isfinite(stat)
    # Must serialize with allow_nan=False (what Postgres jsonb enforces): a
    # float NaN/Infinity anywhere would raise here. Literal string cells like
    # "NaN" are fine — they're just categorical values.
    json.dumps(p.model_dump(mode="json"), allow_nan=False)


def test_identifier_survives_a_single_null() -> None:
    # A real id column with one missing value must stay 'identifier'.
    data = b"order_id,amt\nA1,10\nA2,20\n,30\nA4,40\n"
    p = profile_dataset(data, "csv", "ds", "v1")
    oid = next(c for c in p.columns if c.name == "order_id")
    assert oid.canonical_type == "identifier"
    assert oid.candidate_role == "identifier"
    assert oid.null_count == 1


def test_clean_numeric_column_still_numeric() -> None:
    # The stricter parser must not reject legitimate numbers.
    data = b"v\n1\n2.5\n1e3\n-4\n1,000\n"
    p = profile_dataset(data, "csv", "ds", "v1")
    col = next(c for c in p.columns if c.name == "v")
    assert col.canonical_type in ("numeric", "identifier")
    if col.canonical_type == "numeric":
        assert col.min == -4.0 and col.max == 1000.0
