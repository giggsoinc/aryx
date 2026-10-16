"""Regression coverage for a real data-corruption bug found this session.

primary_type_and_keys() picks the ontology_type a batch-uploaded file gets,
from the LLM-drafted graph_plan's `primary_types` list (each entry names
which source_file it covers). Before this fix, a file with no matching
entry silently fell back to `primary_types[0]` — the FIRST file's type,
regardless of any real resemblance. Live in workspace 48 (MSI_SRM), a
6-file batch upload's plan only explicitly covered the first couple of
files; every later, unmatched file (contract_lines.csv, product_transitions.csv,
ANSWER_KEY.csv) got dumped into primary_types[0]'s type ("GoldenParty"
in that run) purely by batch position, producing a disconnected,
21,000+-entity garbage-collection bucket mixing four unrelated row shapes.
"""
from __future__ import annotations

from aryx.pipeline.smart_understand import primary_type_and_keys

_PLAN = {
    "primary_types": [
        {"name": "GoldenParty", "source_file": "golden_party_lookup.csv",
         "match_keys": ["golden_party_id"]},
        {"name": "Account", "source_file": "contracts.csv", "match_keys": ["account_number"]},
    ],
}


def test_matching_source_file_returns_its_own_type() -> None:
    name, keys = primary_type_and_keys(_PLAN, "contracts.csv")
    assert name == "Account" and keys == ["account_number"]


def test_unmatched_file_does_not_fall_back_to_the_first_type() -> None:
    # The real bug: contract_lines.csv has no entry in the plan at all —
    # it must NOT silently become "GoldenParty" (primary_types[0]).
    name, keys = primary_type_and_keys(_PLAN, "contract_lines.csv")
    assert (name, keys) == ("", [])


def test_no_filename_still_uses_the_first_type_unchanged() -> None:
    # Original, unchanged behavior for a caller with no specific file in
    # mind at all (there is exactly one real caller today and it always
    # passes a filename, but this contract predates that and other callers
    # may rely on it).
    name, keys = primary_type_and_keys(_PLAN, "")
    assert name == "GoldenParty" and keys == ["golden_party_id"]


def test_empty_plan_returns_the_generic_default() -> None:
    assert primary_type_and_keys(None, "anything.csv") == ("", [])
    assert primary_type_and_keys({}, "") == ("Record", ["name"])


def test_match_keys_missing_from_matched_entry_defaults_to_name() -> None:
    plan = {"primary_types": [{"name": "Widget", "source_file": "widgets.csv"}]}
    assert primary_type_and_keys(plan, "widgets.csv") == ("Widget", ["name"])
