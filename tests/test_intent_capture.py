"""Tests for User Intent Capture (C01) — pure, no DB, no LLM."""
from __future__ import annotations

from aryx.intent import UserIntentRequest, capture_intent
from aryx.intent.models import DateRange


def _contracts_request(**overrides: object) -> UserIntentRequest:
    """The reference contract from the C01 spec, with optional field overrides."""
    base: dict[str, object] = {
        "uploaded_file": "contracts_1000.csv",
        "domain": "contract_management",
        "objective": "Show contract renewal performance and identify regions with weak renewal outcomes",
        "preferred_kpis": ["renewal rate", "renewed contract value"],
        "preferred_dimensions": ["region"],
        "preferred_chart_types": ["bar"],
        "target_audience": "sales leadership",
    }
    base.update(overrides)
    return UserIntentRequest(**base)


def test_reference_contract_is_valid() -> None:
    intent = capture_intent(_contracts_request())
    assert intent.validation_status == "valid"
    assert intent.errors == []
    assert intent.warnings == []
    assert intent.schema_version == "1.0"
    assert intent.domain == "contract_management"
    assert intent.preferences.preferred_kpis == ["renewal rate", "renewed contract value"]
    assert intent.preferences.preferred_chart_types == ["bar"]
    assert intent.preferences.target_audience == "sales leadership"


def test_correlation_id_generated_when_absent() -> None:
    intent = capture_intent(_contracts_request())
    assert intent.request_id.startswith("req_")
    assert len(intent.request_id) > len("req_")


def test_correlation_id_honored_when_supplied() -> None:
    intent = capture_intent(_contracts_request(request_id="req_contracts_001"))
    assert intent.request_id == "req_contracts_001"
    # Explicit argument wins over the request field.
    intent2 = capture_intent(_contracts_request(request_id="req_x"), request_id="req_y")
    assert intent2.request_id == "req_y"


def test_blank_objective_blocks() -> None:
    intent = capture_intent(_contracts_request(objective="   "))
    assert intent.validation_status == "invalid"
    assert any("objective is required" in e for e in intent.errors)


def test_missing_domain_and_file_block() -> None:
    intent = capture_intent(_contracts_request(domain="", uploaded_file=""))
    assert intent.validation_status == "invalid"
    assert any("domain is required" in e for e in intent.errors)
    assert any("uploaded_file is required" in e for e in intent.errors)


def test_unsupported_chart_type_warns_but_stays_valid() -> None:
    intent = capture_intent(_contracts_request(preferred_chart_types=["bar", "hologram"]))
    assert intent.validation_status == "valid"
    assert any("hologram" in w for w in intent.warnings)
    # Retained, not dropped (fallback: keep unsupported preference).
    assert "hologram" in intent.preferences.preferred_chart_types


def test_unsupported_audience_warns() -> None:
    intent = capture_intent(_contracts_request(target_audience="martians"))
    assert intent.validation_status == "valid"
    assert any("martians" in w for w in intent.warnings)
    assert intent.preferences.target_audience == "martians"


def test_normalization_whitespace_and_list_dedupe() -> None:
    intent = capture_intent(_contracts_request(
        objective="  Show   renewal    performance  ",
        preferred_dimensions=[" region ", "Region", "", "product"],
    ))
    assert intent.objective == "Show renewal performance"
    # Case-insensitive dedupe, blanks dropped, order + first casing preserved.
    assert intent.preferences.preferred_dimensions == ["region", "product"]


def test_chart_type_catalogue_is_case_insensitive() -> None:
    intent = capture_intent(_contracts_request(preferred_chart_types=["BAR", "Line"]))
    assert intent.warnings == []
    assert intent.validation_status == "valid"


def test_date_range_normalized_to_iso() -> None:
    intent = capture_intent(_contracts_request(
        date_range=DateRange(start="2026/01/15", end="2026-03-31"),
    ))
    assert intent.validation_status == "valid"
    assert intent.preferences.date_range is not None
    assert intent.preferences.date_range.start == "2026-01-15"
    assert intent.preferences.date_range.end == "2026-03-31"


def test_inconsistent_date_range_blocks() -> None:
    intent = capture_intent(_contracts_request(
        date_range=DateRange(start="2026-06-01", end="2026-01-01"),
    ))
    assert intent.validation_status == "invalid"
    assert any("after end" in e for e in intent.errors)


def test_unparseable_date_blocks() -> None:
    intent = capture_intent(_contracts_request(
        date_range=DateRange(start="not-a-date", end="2026-01-01"),
    ))
    assert intent.validation_status == "invalid"
    assert any("not a valid date" in e for e in intent.errors)
