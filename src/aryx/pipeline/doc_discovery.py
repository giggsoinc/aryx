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
        return {"ontology_type": otype, "match_keys": d.get("match_keys") or ["name"]}
    except Exception:  # noqa: BLE001
        return {"ontology_type": fallback, "match_keys": ["name"]}


def read_files(doc_paths: list[Path], tabular: list[tuple[bytes, str]],
               broker: Broker, context: str) -> dict[str, Any]:
    """Read everything; return {mentions, tabular, summary} without committing."""
    settings = get_settings()
    mentions = []
    if doc_paths:
        connector = DocumentRouterConnector(
            paths=doc_paths, system="document", broker=broker,
            chunk_store=ChunkStore(settings.rdb_dsn), chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap, expected_embed_dim=settings.embed_dim)
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
