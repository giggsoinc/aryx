"""Unit tests for derive_entities_by_column's grouping/survivorship logic —
the one genuinely new piece of logic in the derive-a-type feature (the API
route itself is a thin pass-through, covered in test_api_routes.py).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from aryx.pipeline.derive_entities import derive_entities_by_column


def _run(entities, member_landed_ids=None, **kwargs):
    estore = MagicMock()
    estore.list_entities.return_value = entities
    estore.member_landed_ids.return_value = member_landed_ids or {}
    estore.save.side_effect = lambda to_save: len(to_save)
    ostore = MagicMock()
    ostore.list_types.return_value = []

    with patch("aryx.pipeline.derive_entities.EntityStore", return_value=estore), \
         patch("aryx.pipeline.derive_entities.OntologyStore", return_value=ostore), \
         patch("aryx.pipeline.derive_entities.FalkorStore"), \
         patch("aryx.pipeline.derive_entities.project_graph",
               return_value={"entities": 0, "relationships": 0}), \
         patch("aryx.pipeline.derive_entities._build_type_ancestors", return_value={}):
        result = derive_entities_by_column("dsn", "graph_url", 29, **kwargs)
    return result, estore, ostore


def test_case_insensitive_grouping_folds_together():
    entities = [
        (1, "ContractLineItem", {"Customer Number": "ABC-1"}),
        (2, "ContractLineItem", {"Customer Number": "abc-1"}),
        (3, "ContractLineItem", {"Customer Number": "XYZ-2"}),
    ]
    result, estore, _ = _run(entities, source_type="ContractLineItem",
                              group_by_attr="Customer Number", new_type_name="Customer")
    assert result["source_groups"] == 2
    assert result["created"] == 2
    saved = estore.save.call_args[0][0]
    keys = {entity.attributes["Customer Number"] for entity, _ in saved}
    assert keys == {"ABC-1", "XYZ-2"}


def test_missing_key_rows_are_skipped_and_counted():
    entities = [
        (1, "ContractLineItem", {"Customer Number": "ABC-1"}),
        (2, "ContractLineItem", {}),
        (3, "ContractLineItem", {"Customer Number": ""}),
        (4, "Other", {"Customer Number": "ZZZ"}),  # different type, ignored entirely
    ]
    result, _, _ = _run(entities, source_type="ContractLineItem",
                         group_by_attr="Customer Number", new_type_name="Customer")
    assert result["source_groups"] == 1
    assert result["skipped_missing_key"] == 2


def test_first_non_empty_wins_survivorship_for_carry_attrs():
    entities = [
        (1, "ContractLineItem", {"Customer Number": "ABC-1", "Customer Name": ""}),
        (2, "ContractLineItem", {"Customer Number": "abc-1", "Customer Name": "Acme Inc"}),
        (3, "ContractLineItem", {"Customer Number": "ABC-1", "Customer Name": "Ignored Co"}),
    ]
    result, estore, _ = _run(entities, source_type="ContractLineItem",
                              group_by_attr="Customer Number", new_type_name="Customer",
                              carry_attrs=["Customer Name"])
    assert result["source_groups"] == 1
    entity, _ = estore.save.call_args[0][0][0]
    assert entity.attributes["Customer Name"] == "Acme Inc"


def test_provenance_is_union_of_group_landed_ids():
    entities = [
        (1, "ContractLineItem", {"Customer Number": "ABC-1"}),
        (2, "ContractLineItem", {"Customer Number": "abc-1"}),
    ]
    result, estore, _ = _run(
        entities, member_landed_ids={1: [101], 2: [102, 103]},
        source_type="ContractLineItem", group_by_attr="Customer Number",
        new_type_name="Customer",
    )
    assert result["created"] == 1
    _, members = estore.save.call_args[0][0][0]
    assert sorted(m.landed_record_id for m in members) == [101, 102, 103]
