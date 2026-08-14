from __future__ import annotations

import json

from aryx.api.file_ingest_api import _colvals
from aryx.pipeline.doc_discovery import _infer_type, infer_fk_links


def _json(rows: list[dict]) -> bytes:
    return json.dumps(rows).encode("utf-8")


def test_json_colvals_flattens_rows_for_fk_discovery() -> None:
    data = _json([
        {"model": "input.item", "fields": {"name": "chair"}},
        {"model": "input.item", "fields": {"name": "table"}},
    ])

    assert _colvals(data, ".json") == {
        "colvals": {
            "model": ["input.item", "input.item"],
            "fields.name": ["chair", "table"],
        }
    }


def test_json_colvals_handles_bom_prefixed_input() -> None:
    # dataset/formats.py accepts BOM-prefixed JSON (utf-8-sig) at ingest, so
    # FK-discovery must decode the same way instead of raising on the BOM.
    data = b"\xef\xbb\xbf" + _json([
        {"model": "input.item", "fields": {"name": "chair"}},
    ])

    assert _colvals(data, ".json") == {
        "colvals": {
            "model": ["input.item"],
            "fields.name": ["chair"],
        }
    }


def test_json_model_discriminator_drives_type_and_match_keys() -> None:
    plan = _infer_type(
        '[{"model":"input.operationmaterial","fields":{'
        '"operation_id":"Saw chair leg","item_id":"chair leg","type":"end"}}]',
        "input_operationmaterial.json",
        "",
    )

    assert plan == {
        "ontology_type": "OperationMaterial",
        "match_keys": ["fields.operation_id", "fields.item_id", "fields.type"],
    }


def test_json_fk_links_use_flattened_id_fields() -> None:
    item = _colvals(_json([
        {"model": "input.item", "fields": {"name": "chair leg"}},
        {"model": "input.item", "fields": {"name": "wooden beam"}},
    ]), ".json")
    operation = _colvals(_json([
        {"model": "input.operation", "fields": {"name": "Saw chair leg"}},
        {"model": "input.operation", "fields": {"name": "Saw table leg"}},
    ]), ".json")
    material = _colvals(_json([
        {
            "model": "input.operationmaterial",
            "fields": {
                "operation_id": "Saw chair leg",
                "item_id": "chair leg",
                "type": "end",
            },
        },
        {
            "model": "input.operationmaterial",
            "fields": {
                "operation_id": "Saw chair leg",
                "item_id": "wooden beam",
                "type": "start",
            },
        },
    ]), ".json")

    links = infer_fk_links([
        {"ontology_type": "Item", **item},
        {"ontology_type": "Operation", **operation},
        {"ontology_type": "OperationMaterial", **material},
    ])

    assert {
        "source_type": "OperationMaterial",
        "source_attr": "fields.item_id",
        "target_type": "Item",
        "target_attr": "fields.name",
        "name": "OPERATIONMATERIAL_ITEM",
    } in links
    assert {
        "source_type": "OperationMaterial",
        "source_attr": "fields.operation_id",
        "target_type": "Operation",
        "target_attr": "fields.name",
        "name": "OPERATIONMATERIAL_OPERATION",
    } in links
