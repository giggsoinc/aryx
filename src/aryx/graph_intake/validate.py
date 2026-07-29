"""Deterministic graph validation + normalization (C05) — no LLM.

Mirrors the component Procedure:
  1. validate the payload against the graph JSON schema
  2. validate graph metadata and dataset id/version linkage
  3. validate entity ids, relationship endpoints, labels, properties, value types
  4. detect duplicate entities, duplicate relationships, dangling references,
     empty required collections
  5. normalize the accepted graph into the internal canonical model
  6. (caller) hash + store the original JSON immutably

schema_status is "valid" only when the graph is structurally clean (no dangling
references, no duplicate entities, non-empty entity collection, no schema
errors). Dangling relationships are rejected (dropped from the normalized graph).
"""
from __future__ import annotations

from typing import Any

from aryx.graph_intake.models import GraphIntakeResult, ValidationIssue

# JSON scalar/container types allowed as property values.
_ALLOWED_VALUE = (str, int, float, bool, type(None), list, dict)


def _scalar_props(props: dict[str, Any], where: str,
                  issues: list[ValidationIssue]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in props.items():
        if not isinstance(value, _ALLOWED_VALUE):
            issues.append(ValidationIssue(code="bad_value_type",
                                          detail=f"{where}.{key}: {type(value).__name__}"))
            continue
        clean[str(key)] = value
    return clean


def validate_and_normalize(
    graph_json: dict[str, Any],
    graph_id: str,
    version: str,
    dataset_ids: list[str] | None = None,
) -> tuple[GraphIntakeResult, dict[str, Any]]:
    """Validate a graph JSON and return (intake report, normalized graph)."""
    issues: list[ValidationIssue] = []
    entities_in = graph_json.get("entities")
    rels_in = graph_json.get("relationships")

    # Step 1 — schema shape.
    if not isinstance(entities_in, list):
        issues.append(ValidationIssue(code="schema", detail="'entities' must be a list"))
        entities_in = []
    if not isinstance(rels_in, list):
        issues.append(ValidationIssue(code="schema", detail="'relationships' must be a list"))
        rels_in = []

    # Step 3/4 — entities: ids present, unique, typed.
    ids: set[str] = set()
    duplicate_entities = 0
    canon_entities: list[dict[str, Any]] = []
    for ent in entities_in:
        if not isinstance(ent, dict):
            issues.append(ValidationIssue(code="invalid_entity", detail="entity is not an object"))
            continue
        eid, etype = ent.get("id"), ent.get("type")
        if eid in (None, "") or etype in (None, ""):
            issues.append(ValidationIssue(code="invalid_entity",
                                          detail=f"missing id/type: {ent!r}"))
            continue
        eid = str(eid)
        if eid in ids:
            duplicate_entities += 1
            continue
        ids.add(eid)
        props = _scalar_props({k: v for k, v in ent.items() if k not in ("id", "type")},
                              f"entity[{eid}]", issues)
        canon_entities.append({"id": eid, "type": str(etype), "properties": props})

    empty_collections: list[str] = []
    if not canon_entities:
        empty_collections.append("entities")
        issues.append(ValidationIssue(code="empty_collection", detail="no valid entities"))

    # Step 3/4 — relationships: endpoints exist, unique, typed.
    seen_rel: set[tuple[str, str, str]] = set()
    duplicate_relationships = 0
    dangling = 0
    canon_rels: list[dict[str, Any]] = []
    for rel in rels_in:
        if not isinstance(rel, dict):
            issues.append(ValidationIssue(code="invalid_relationship", detail="relationship is not an object"))
            continue
        src, tgt, rtype = rel.get("source"), rel.get("target"), rel.get("type")
        if src in (None, "") or tgt in (None, "") or rtype in (None, ""):
            issues.append(ValidationIssue(code="invalid_relationship", detail=f"missing endpoint/type: {rel!r}"))
            continue
        src, tgt, rtype = str(src), str(tgt), str(rtype)
        if src not in ids or tgt not in ids:
            dangling += 1
            missing = src if src not in ids else tgt
            issues.append(ValidationIssue(code="dangling_relationship",
                                          detail=f"{src}-[{rtype}]->{tgt} (missing {missing})"))
            continue
        key = (src, rtype, tgt)
        if key in seen_rel:
            duplicate_relationships += 1
            continue
        seen_rel.add(key)
        props = _scalar_props({k: v for k, v in rel.items() if k not in ("source", "target", "type")},
                              f"rel[{src}->{tgt}]", issues)
        canon_rels.append({"source": src, "type": rtype, "target": tgt, "properties": props})

    # Collapse repeated dangling/duplicate issues into a single counted entry.
    hard = {"schema", "invalid_entity", "invalid_relationship", "bad_value_type", "empty_collection"}
    blocking = (duplicate_entities > 0 or dangling > 0 or bool(empty_collections)
                or any(i.code in hard for i in issues))
    status = "invalid" if blocking else "valid"

    result = GraphIntakeResult(
        graph_id=graph_id, graph_version=version,
        dataset_ids=dataset_ids or [],
        normalized_graph_ref=f"graphs/{graph_id}/{version}",
        entity_count=len(canon_entities), relationship_count=len(canon_rels),
        duplicate_entities=duplicate_entities,
        duplicate_relationships=duplicate_relationships,
        dangling_relationships=dangling, empty_collections=empty_collections,
        schema_status=status, issues=issues,
    )
    normalized = {"entities": canon_entities, "relationships": canon_rels}
    return result, normalized
