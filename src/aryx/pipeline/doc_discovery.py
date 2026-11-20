"""Document self-discovery: read files, surface discovered types, ingest on OK.

Reading runs the document pipeline (chunk → PII → embed → extract) and keeps
each mention's *own* discovered type instead of pinning one. Tabular files
(JSON/CSV) get a single type inferred from a sample. Nothing lands until the
user confirms which types to keep.
"""
from __future__ import annotations

import csv
import json
import logging
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from aryx import llm_runtime
from aryx.broker import Broker
from aryx.config import get_settings
from aryx.connectors.csv_source import CsvConnector
from aryx.connectors.doc_router import DocumentRouterConnector
from aryx.connectors.json_source import JsonConnector
from aryx.connectors.json_source import _flatten
from aryx.connectors.records_source import RecordsConnector
from aryx.pipeline.orchestrate import link_entities, run_pipeline
from aryx.store.chunk_store import ChunkStore

logger = logging.getLogger(__name__)

DOC_EXTS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".rtf",
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
DATA_EXTS = {".json", ".csv"}


_GENERIC = {"table", "row", "record", "data", "file", "entity", "item", "object", "dataset"}

_MODEL_TYPES = {
    "common.parameter": "Parameter",
    "common.userpreference": "UserPreference",
    "input.buffer": "Buffer",
    "input.calendar": "Calendar",
    "input.calendarbucket": "CalendarBucket",
    "input.customer": "Customer",
    "input.demand": "Demand",
    "input.item": "Item",
    "input.itemdistribution": "ItemDistribution",
    "input.itemsupplier": "ItemSupplier",
    "input.location": "Location",
    "input.operation": "Operation",
    "input.operationmaterial": "OperationMaterial",
    "input.operationplan": "OperationPlan",
    "input.operationresource": "OperationResource",
    "input.resource": "Resource",
    "input.resourceskill": "ResourceSkill",
    "input.skill": "Skill",
    "input.supplier": "Supplier",
}

_MODEL_KEYS = {
    "common.parameter": ["fields.name"],
    "common.userpreference": ["fields.property"],
    "input.buffer": ["fields.id"],
    "input.calendar": ["fields.name"],
    "input.calendarbucket": ["fields.id"],
    "input.customer": ["fields.name"],
    "input.demand": ["fields.name"],
    "input.item": ["fields.name"],
    "input.itemdistribution": ["fields.item_id", "fields.location_id", "fields.origin_id"],
    "input.itemsupplier": ["fields.item_id", "fields.location_id", "fields.supplier_id"],
    "input.location": ["fields.name"],
    "input.operation": ["fields.name"],
    "input.operationmaterial": ["fields.operation_id", "fields.item_id", "fields.type"],
    "input.operationplan": ["fields.reference"],
    "input.operationresource": ["fields.operation_id", "fields.resource_id"],
    "input.resource": ["fields.name"],
    "input.resourceskill": ["fields.resource_id", "fields.skill_id"],
    "input.skill": ["fields.name"],
    "input.supplier": ["fields.name"],
}


def _infer_type(sample: str, filename: str, context: str,
                prefer_header: bool = False) -> dict[str, Any]:
    model_plan = _infer_json_model_type(sample)
    if model_plan:
        return model_plan
    if prefer_header:
        # A table inside a document ("ID | Rule | ...") names its own rows. Asking
        # the model gave a different answer on each run (the Rules table came out
        # as "Requirement" once), which wrecks every count and answer built on it.
        header = _header_type(sample)
        if header and len(header["match_keys"]) >= 2:
            return header

    sys = ("You name the real-world thing each ROW of a data file represents, "
           "for a knowledge graph.")
    user = (f"Goal: {context or 'general knowledge graph'}\nFile: {filename}\n"
            f"Sample rows:\n{sample[:600]}\n\nWhat real-world entity is each row? "
            "Use a concrete singular noun like Customer, Company, Product, Order — "
            "NEVER generic words like Table, Row, Record, or Data. Reply ONLY as JSON "
            '{"ontology_type":"SingularPascalCase","match_keys":["the 1-2 columns '
            'that name/identify a row"]}.')
    fallback = _header_type(sample) or {
        "ontology_type": Path(filename).stem.replace("_", " ").title().replace(" ", ""),
        "match_keys": ["name"]}
    # Retried: a dropped connection or one slow Gemini call must not decide a
    # table's type (it is the name everything built on the table carries).
    for attempt in (1, 2, 3):
        try:
            txt = llm_runtime.chat("menial", sys, user)[0]
            s, e = txt.find("{"), txt.rfind("}")
            d = json.loads(txt[s:e + 1])
            otype = (d.get("ontology_type") or "").strip()
            if not otype or otype.lower() in _GENERIC:
                return fallback
            return {"ontology_type": otype, "match_keys": _clean_keys(d.get("match_keys"))}
        except Exception as exc:  # noqa: BLE001
            logger.warning("type inference attempt %d failed for %s (%s: %.80s)",
                           attempt, filename, type(exc).__name__, str(exc))
            if attempt < 3:
                time.sleep(1.5 * attempt)
    return fallback


# Words dropped from a header when it is turned into a type name.
_FILLER_WORDS = {"in", "this", "as", "is", "of", "the", "a", "an", "for", "to", "and", "or"}

# Header words that name a column, not the thing a row is.
_NOT_A_TYPE = {"who", "what", "when", "where", "why", "how", "term", "name", "item",
               "description", "notes", "note", "status", "type", "value", "meaning",
               "id", "no", "number", "key", "code", "title", "comment", "comments",
               "priority", "attr", "attrs", "owner", "impact", "severity", "target",
               "recommendation", "consequence", "criteria"}


def _header_type(sample: str) -> dict[str, Any] | None:
    """Name a table's row type from its own header, with no model.

    ``ID | Decision | Status`` -> Decision (keys ID + Decision): the first column
    that is neither an identifier nor a generic word names the thing. Used when
    the model cannot be reached, instead of a name made from the file name.
    """
    lines = sample.splitlines()
    if not lines:
        return None
    try:
        header = next(csv.reader([lines[0]]))
    except (csv.Error, StopIteration):
        return None
    ident = next((h for h in header if h.strip().lower() in ("id", "key", "code")), None)
    for col in header:
        word = re.sub(r"\([^)]*\)", " ", col).strip()       # "Today (as-is)" -> "Today"
        norm = re.sub(r"[^a-z]", "", word.lower())
        if len(norm) < 3 or norm in _NOT_A_TYPE or norm.endswith("id"):
            continue
        parts = [w for w in re.split(r"[^A-Za-z0-9]+", word)
                 if w and w.lower() not in _FILLER_WORDS][:3]
        if parts and parts[-1].lower().endswith("s"):
            parts[-1] = _singular_stem(parts[-1])
        otype = "".join(w[:1].upper() + w[1:] for w in parts)
        if not otype:
            continue
        keys = [k for k in (ident, col) if k]
        return {"ontology_type": otype, "match_keys": keys}
    return None


def _infer_json_model_type(sample: str) -> dict[str, Any] | None:
    """Use a JSON record's model discriminator before asking the LLM.

    FrePPLe-style exports encode the business object in ``model`` and the row's
    attributes in ``fields``. That signal is more precise than a short sample
    prompt, especially for supply-chain data where many rows mention customers,
    products, suppliers, and locations as references rather than row types.
    """
    match = re.search(r'"model"\s*:\s*"([^"]+)"', sample)
    if not match:
        return None
    model = match.group(1).strip()
    otype = _MODEL_TYPES.get(model)
    if not otype:
        leaf = re.split(r"[._-]+", model)[-1]
        otype = leaf.title().replace(" ", "")
    keys = _MODEL_KEYS.get(model, ["fields.name"])
    return {"ontology_type": otype, "match_keys": keys}


def _json_colvals(data: bytes) -> dict[str, list[str]]:
    """Flatten JSON rows into column values for cross-file FK inference."""
    try:
        loaded = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return {}
    rows = loaded if isinstance(loaded, list) else [loaded]
    cols: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for k, v in _flatten(row).items():
            if v is not None:
                cols.setdefault(k, []).append(str(v).strip())
    return cols


def _clean_keys(raw: Any) -> list[str]:
    """Coerce a model's match_keys to a flat list of non-empty column strings.

    The small local model sometimes returns a bare string or a nested list;
    an unhashable element (a list) later blows up ``payload.get(key)`` with
    'unhashable type: list'. Flatten one level, keep only scalar names.
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return ["name"]
    keys: list[str] = []
    for k in raw:
        for item in (k if isinstance(k, list) else [k]):
            if isinstance(item, (str, int, float)) and str(item).strip():
                keys.append(str(item).strip())
    return keys or ["name"]


def _singular_stem(type_name: str) -> str:
    """Lowercase singular stem of a type name for FK-column name matching."""
    t = type_name.lower()
    if t.endswith("ies"):
        return t[:-3]          # Companies -> compan(y)
    if t.endswith("s") and not t.endswith("ss"):
        return t[:-1]          # Customers -> customer
    return t


# A bare "ID" / "name" is in every table: sharing it says nothing about links.
_GENERIC_COLS = {"id", "name", "key", "code", "no", "number", "type", "title", "label"}


def _col(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def infer_fk_links(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Discover foreign-key links across ingested tabular files by value overlap.

    Deterministic — no LLM (small local models return unstable column names and
    directions). A link ``src.col -> tgt.col`` is proposed when:
      * the target column is a candidate key (all values distinct, ≥2 rows),
      * most of the source column's values are contained in it, and
      * the source column name references the target type (typical FK naming,
        e.g. ``CustomerID`` -> ``Customer``), which also fixes direction so a
        shared natural key (``Company`` on both sides) links only one way.
    ``link_by_attribute`` still materializes edges only on exact value matches,
    so the proposal can never create a spurious edge.

    Args:
        files: One dict per file with ``ontology_type`` and ``colvals``
            (mapping column name -> list of that column's raw values).

    Returns:
        A list of ``{source_type, source_attr, target_type, target_attr,
        name}`` specs (possibly empty).
    """
    if len(files) < 2:
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for src in files:
        for tgt in files:
            if src is tgt:
                continue
            tstem = _singular_stem(tgt["ontology_type"])
            for tcol, tvals in (tgt.get("colvals") or {}).items():
                tset = {v for v in tvals if v}
                # Target column must be a candidate key: distinct, non-trivial.
                if len(tset) < 2 or len(tset) != len([v for v in tvals if v]):
                    continue
                for scol, svals in (src.get("colvals") or {}).items():
                    sset = {v for v in svals if v}
                    if not sset or len(sset & tset) / len(sset) < 0.6:
                        continue
                    # Direction via FK naming: the source column names the
                    # target entity (CustomerID->Customer, Company->Company).
                    names_target = len(tstem) >= 3 and tstem in scol.lower().replace("_", "")
                    # ...or the two tables share the column's name ("Dept ID" in
                    # Employees and Departments) and the target holds more
                    # distinct values (or the source repeats its values): the
                    # side that holds each value once is the referenced one.
                    repeats = len([v for v in svals if v]) > len(sset)
                    shared = (_col(scol) == _col(tcol)
                              and _col(scol) not in _GENERIC_COLS
                              and (repeats or len(tset) > len(sset)))
                    if not (names_target or shared):
                        continue
                    key = (src["ontology_type"], scol, tgt["ontology_type"], tcol)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "source_type": src["ontology_type"], "source_attr": scol,
                        "target_type": tgt["ontology_type"], "target_attr": tcol,
                        "name": f"{src['ontology_type']}_{tgt['ontology_type']}".upper(),
                    })
    logger.info("discovered %d fk-link(s)", len(out))
    return out


def read_files(doc_paths: list[Path], tabular: list[tuple[bytes, str]],
               broker: Broker, context: str) -> dict[str, Any]:
    """Read everything; return {mentions, tabular, summary} without committing."""
    settings = get_settings()
    mentions = []
    if doc_paths:
        connector = DocumentRouterConnector(
            paths=doc_paths, system="document", broker=broker,
            chunk_store=ChunkStore(settings.rdb_dsn), chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap, expected_embed_dim=settings.embed_dim,
            context=context)
        mentions = list(connector.extract())

    tab_plans = [{"filename": n, "data": d,
                  **_infer_type(d[:800].decode("utf-8", "ignore"), n, context)}
                 for d, n in tabular]

    by_type: dict[str, list[str]] = {}
    for m in mentions:
        by_type.setdefault(m.payload["type"], []).append(m.payload["name"])
    types = [{"type": t, "count": len(v), "examples": list(dict.fromkeys(v))[:5]}
             for t, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))]
    files = [{"filename": p["filename"], "ontology_type": p["ontology_type"]} for p in tab_plans]
    return {"mentions": mentions, "tabular": tab_plans,
            "summary": {"types": types, "files": files}}


def ingest_confirmed(data: dict[str, Any], approved_types: list[str],
                     approved_files: list[str], broker: Broker, jobs, job_id: str,
                     workspace_id: int = 1) -> None:
    """Resolve + project the approved discovered types and tabular files."""
    settings = get_settings()
    total = max(len(approved_types) + len(approved_files), 1)
    step = 0
    link_plans: list[dict[str, Any]] = []
    for otype in approved_types:
        step += 1
        jobs.update_stage(job_id, f"{step}/{total}", int(step * 90 / total), f"Adding {otype}")
        recs = [m for m in data["mentions"] if m.payload.get("type") == otype]
        if recs:
            run_pipeline(connector=RecordsConnector(recs), dsn=settings.rdb_dsn,
                         system="document", dataset=otype, ontology_type=otype,
                         match_keys=["name"], broker=broker,
                         workspace_id=workspace_id)
    for fname in approved_files:
        step += 1
        plan = next((p for p in data["tabular"] if p["filename"] == fname), None)
        if not plan:
            continue
        jobs.update_stage(job_id, f"{step}/{total}", int(step * 90 / total), f"Adding {fname}")
        tmp_path: Path | None = None
        if Path(fname).suffix.lower() == ".json":
            tmp = NamedTemporaryFile(suffix=".json", delete=False)
            tmp.write(plan["data"])
            tmp.close()
            tmp_path = Path(tmp.name)
            conn = JsonConnector(tmp_path, system="json", dataset=Path(fname).stem)
            link_plans.append({
                "ontology_type": plan["ontology_type"],
                "colvals": _json_colvals(plan["data"]),
            })
        else:
            conn = CsvConnector(plan["data"], system="csv", dataset=Path(fname).stem)
            link_plans.append({
                "ontology_type": plan["ontology_type"],
                "colvals": _csv_colvals(plan["data"]),
            })
        try:
            run_pipeline(connector=conn, dsn=settings.rdb_dsn,
                         system=Path(fname).suffix.lstrip("."), dataset=Path(fname).stem,
                         ontology_type=plan["ontology_type"], match_keys=plan["match_keys"],
                         broker=broker, workspace_id=workspace_id)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
    inferred = infer_fk_links(link_plans)
    if inferred:
        jobs.update_stage(job_id, "Link", 92, "Inferring relationships")
        link_entities(settings.rdb_dsn, workspace_id, inferred)


def _csv_colvals(data: bytes) -> dict[str, list[str]]:
    """Return CSV column values for confirmed-ingest relationship discovery."""
    import csv
    import io

    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8", "ignore")))
        cols: dict[str, list[str]] = {}
        for row in reader:
            for k, v in row.items():
                if k is not None:
                    cols.setdefault(k, []).append((v or "").strip())
        return cols
    except csv.Error:
        return {}
