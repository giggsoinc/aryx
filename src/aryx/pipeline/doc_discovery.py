"""Document self-discovery: read files, surface discovered types, ingest on OK.

Reading runs the document pipeline (chunk → PII → embed → extract) and keeps
each mention's *own* discovered type instead of pinning one. Tabular files
(JSON/CSV) get a single type inferred from a sample. Nothing lands until the
user confirms which types to keep.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from aryx import llm_runtime
from aryx.broker import Broker
from aryx.config import get_settings
from aryx.connectors.csv_source import CsvConnector
from aryx.connectors.doc_router import DocumentRouterConnector
from aryx.connectors.json_source import JsonConnector
from aryx.connectors.records_source import RecordsConnector
from aryx.pipeline.orchestrate import run_pipeline
from aryx.store.chunk_store import ChunkStore

logger = logging.getLogger(__name__)

DOC_EXTS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".rtf",
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
DATA_EXTS = {".json", ".csv"}


_GENERIC = {"table", "row", "record", "data", "file", "entity", "item", "object", "dataset"}


def _infer_type(sample: str, filename: str, context: str) -> dict[str, Any]:
    sys = ("You name the real-world thing each ROW of a data file represents, "
           "for a knowledge graph.")
    user = (f"Goal: {context or 'general knowledge graph'}\nFile: {filename}\n"
            f"Sample rows:\n{sample[:600]}\n\nWhat real-world entity is each row? "
            "If the Goal explicitly names the entity/type this file represents, "
            "you MUST use that exact type name (singularised, PascalCase); only "
            "infer the type from the columns when the Goal does not name it. "
            "Use a concrete singular noun like Customer, Company, Product, Order — "
            "NEVER generic words like Table, Row, Record, or Data. Reply ONLY as JSON "
            '{"ontology_type":"SingularPascalCase","match_keys":["the 1-2 columns '
            'that name/identify a row"]}.')
    fallback = Path(filename).stem.replace("_", " ").title().replace(" ", "")
    try:
        txt = llm_runtime.chat("menial", sys, user)[0]
        s, e = txt.find("{"), txt.rfind("}")
        d = json.loads(txt[s:e + 1])
        otype = (d.get("ontology_type") or "").strip()
        if not otype or otype.lower() in _GENERIC:
            otype = fallback
        return {"ontology_type": otype, "match_keys": _clean_keys(d.get("match_keys"))}
    except Exception:  # noqa: BLE001
        return {"ontology_type": fallback, "match_keys": ["name"]}


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
                    if len(tstem) < 3 or tstem not in scol.lower().replace("_", ""):
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
    for otype in approved_types:
        step += 1
        jobs.update_stage(job_id, f"{step}/{total}", int(step * 90 / total), f"Adding {otype}")
        recs = [m for m in data["mentions"] if m.payload.get("type") == otype]
        if recs:
            run_pipeline(connector=RecordsConnector(recs), dsn=settings.rdb_dsn,
                         system="document", dataset=otype, ontology_type=otype,
                         match_keys=["name"], graph_url=settings.graph_url, broker=broker,
                         workspace_id=workspace_id)
    for fname in approved_files:
        step += 1
        plan = next((p for p in data["tabular"] if p["filename"] == fname), None)
        if not plan:
            continue
        jobs.update_stage(job_id, f"{step}/{total}", int(step * 90 / total), f"Adding {fname}")
        if Path(fname).suffix.lower() == ".json":
            tmp = NamedTemporaryFile(suffix=".json", delete=False)
            tmp.write(plan["data"])
            tmp.close()
            conn = JsonConnector(Path(tmp.name), system="json")
        else:
            conn = CsvConnector(plan["data"], system="csv", dataset=Path(fname).stem)
        run_pipeline(connector=conn, dsn=settings.rdb_dsn,
                     system=Path(fname).suffix.lstrip("."), dataset=Path(fname).stem,
                     ontology_type=plan["ontology_type"], match_keys=plan["match_keys"],
                     graph_url=settings.graph_url, broker=broker, workspace_id=workspace_id)
