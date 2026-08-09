"""Tests for payload-agnostic infer_relationship (aryx-handoff.md item 3)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from aryx.relationships import infer_relationship


def _broker() -> MagicMock:
    return MagicMock()


def test_missing_name_field_does_not_raise() -> None:
    """LLM returns related=true but omits name — must return (None, 0.0)."""
    with patch("aryx.relationships.complete_json",
               return_value={"related": True, "confidence": 0.8}):
        result = infer_relationship({}, {}, _broker())
    assert result == (None, 0.0)


def test_no_name_key_at_all() -> None:
    """KeyError on result['name'] was the original bug — must not happen."""
    with patch("aryx.relationships.complete_json",
               return_value={"related": True}):
        result = infer_relationship({"PR": "0089922215", "NSN": "8305002619566"},
                                    {"PR": "0099933316", "NSN": "8305002619567"},
                                    _broker())
    assert result == (None, 0.0)


def test_tabular_payload_without_name_key_works() -> None:
    """CSV-sourced payload with no 'name' column must not raise."""
    payload = {
        "PR": "0089922215", "NSN": "8305002619566", "FSC": "8305",
        "Buyer Name": "Matthew Everett", "NOMENCLATURE": "CLOTH,LAMINATED",
    }
    with patch("aryx.relationships.complete_json",
               return_value={"related": False, "name": "", "confidence": 0.0}):
        name, conf = infer_relationship(payload, payload, _broker())
    assert name is None
    assert conf == 0.0


def test_valid_response_returns_name_and_confidence() -> None:
    with patch("aryx.relationships.complete_json",
               return_value={"related": True, "name": "shares_nsn", "confidence": 0.9}):
        name, conf = infer_relationship({"NSN": "123"}, {"NSN": "123"}, _broker())
    assert name == "shares_nsn"
    assert conf == pytest.approx(0.9)


def test_unrelated_returns_none() -> None:
    with patch("aryx.relationships.complete_json",
               return_value={"related": False, "name": "", "confidence": 0.0}):
        assert infer_relationship({}, {}, _broker()) == (None, 0.0)


import pytest
