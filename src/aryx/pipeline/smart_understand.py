"""Brief-led smart understand: customer brief + samples → graph plan.

Provider-agnostic: uses llm_runtime answer role (whatever Settings configured:
Gemini, Claude, OpenAI, Grok, Ollama, …). Deterministic fallbacks when the
model is unavailable so the wizard never hard-stops.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

from aryx import llm_runtime
from aryx.brief import is_populated as brief_is_populated
from aryx.brief import serialize as serialize_brief

logger = logging.getLogger(__name__)

_SAMPLE_ROWS = 12
_DOC_CHARS = 2500

_SYSTEM = """You are Aryx's data understanding agent for a knowledge graph product.
The customer stated what they want BEFORE uploading anything. Their brief is
the goal; the data samples are the evidence. Your job is to read the data
THROUGH that brief, never to replace it.

Given the customer brief and samples from each file/table, you MUST:
1) Infer what the data actually is, in plain language.
2) Restate the brief as understood FROM THE DATA — same six fields, but
   describing what this data can genuinely support. This is a reading, not a
   replacement: keep the customer's domain and aim unless the data flatly
   contradicts them, and say so in `divergences` when it does.
3) Propose a graph plan that SERVES the customer's objectives and proof
   questions — multi-type when columns support dimensions (Merchant,
   Category, Place, Account, Person, Product, …), not one flat row-type.
4) List short follow-up questions only if critical (max 4), easy to answer.
5) Suggest additional documents/tables that would sharpen the graph.
6) Name any objective or proof question in the brief that this data CANNOT
   answer, under `gaps` — an honest gap beats a confident hallucination.

Return ONLY valid JSON with this shape:
{
  "summary": "one paragraph",
  "brief": {
    "domain": "string",
    "aim": "string",
    "objectives": ["string"],
    "scope": "IN: ... OUT: ...",
    "roles": ["string"],
    "questions": ["proof questions the graph must answer"]
  },
  "graph_plan": {
    "primary_types": [
      {"name": "PascalCase", "match_keys": ["col"], "role": "row", "source_file": "optional"}
    ],
    "dimension_types": [
      {"name": "PascalCase", "source_column": "col", "role": "dimension",
       "from_type": "PrimaryType"}
    ],
    "relationships": [
      {"name": "REL_NAME", "from": "TypeA", "to": "TypeB", "via_column": "col"}
    ],
    "outcomes": ["what the user can ask after build"]
  },
  "follow_ups": [{"id": "q1", "question": "...", "why": "..."}],
  "suggested_documents": [
    {"what": "merchant MCC list", "why": "sharper category graph"}
  ],
  "divergences": ["where the data disagrees with what the customer stated"],
  "gaps": ["customer objectives / proof questions this data cannot answer"]
}

Rules:
- Prefer multiple entity types when free-text or categorical columns exist.
- Bank/ledger CSVs: Transaction + Merchant (from description/payee) + Category
  if present; Place/City only if location signals exist.
- match_keys must be real column names from the sample when possible.
- Never use generic type names: Table, Row, Record, Data, Document (unless PDF).
- Be specific to THIS data, not generic enterprise fluff.
- The customer brief outranks your own reading. When they conflict, follow the
  brief in `graph_plan` and record the conflict in `divergences`.
- With no customer brief supplied, draft the six fields cold from the samples.
"""


def sample_bytes(data: bytes, filename: str) -> dict[str, Any]:
    """Build a compact sample dict for one uploaded file."""
    suffix = Path(filename).suffix.lower()
    name = filename or "upload"
    if suffix == ".csv":
        return _sample_csv(data, name)
    if suffix == ".json":
        return _sample_json(data, name)
    # docs / images: text preview only
    text = data[:_DOC_CHARS].decode("utf-8", "ignore")
    if not text.strip():
        text = f"(binary or non-text sample for {name}, {len(data)} bytes)"
    return {
        "filename": name,
        "kind": "document",
        "columns": [],
        "sample_text": text[:_DOC_CHARS],
        "row_estimate": None,
    }


def _sample_csv(data: bytes, name: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8", "ignore")
        reader = csv.DictReader(io.StringIO(text))
        cols = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for i, row in enumerate(reader):
            if i >= _SAMPLE_ROWS:
                break
            rows.append({k: (v or "")[:120] for k, v in row.items() if k})
        # rough row count
        n = text.count("\n")
        lines = []
        lines.append(f"FILE: {name} (csv)")
        lines.append(f"COLUMNS: {', '.join(cols)}")
        lines.append(f"SAMPLE_ROWS ({len(rows)} of ~{max(n - 1, 0)}):")
        for r in rows:
            lines.append(json.dumps(r, ensure_ascii=False)[:400])
        return {
            "filename": name,
            "kind": "tabular",
            "columns": cols,
            "sample_text": "\n".join(lines)[:6000],
            "row_estimate": max(n - 1, 0),
            "sample_rows": rows,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("csv sample failed %s: %s", name, exc)
        return {
            "filename": name,
            "kind": "tabular",
            "columns": [],
            "sample_text": data[:800].decode("utf-8", "ignore"),
            "row_estimate": None,
        }


def _sample_json(data: bytes, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8", "ignore"))
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            cols = list(payload[0].keys())
            rows = payload[:_SAMPLE_ROWS]
            return {
                "filename": name,
                "kind": "tabular",
                "columns": cols,
                "sample_text": (
                    f"FILE: {name} (json array)\nCOLUMNS: {', '.join(cols)}\n"
                    + json.dumps(rows, ensure_ascii=False)[:4000]
                ),
                "row_estimate": len(payload),
                "sample_rows": rows,
            }
        return {
            "filename": name,
            "kind": "document",
            "columns": [],
            "sample_text": json.dumps(payload, ensure_ascii=False)[:_DOC_CHARS],
            "row_estimate": None,
        }
    except Exception:  # noqa: BLE001
        return {
            "filename": name,
            "kind": "document",
            "columns": [],
            "sample_text": data[:_DOC_CHARS].decode("utf-8", "ignore"),
            "row_estimate": None,
        }


def understand_samples(
    samples: list[dict[str, Any]],
    user_hint: str = "",
    customer_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read the samples through the customer brief → understanding + plan.

    `customer_brief` is the brief the customer authored BEFORE uploading.
    When present it anchors the graph plan and is echoed back untouched on
    the result so callers never confuse it with the derived reading.
    """
    if not samples:
        return _empty_result("No samples provided.")

    blob = "\n\n---\n\n".join(
        s.get("sample_text") or s.get("filename") or "" for s in samples
    )
    hint = (user_hint or "").strip()
    brief_text = serialize_brief(customer_brief)
    user = (
        f"Customer brief (authoritative):\n{brief_text or '(none supplied)'}\n\n"
        f"User hint (optional): {hint or '(none)'}\n\n"
        f"Data samples:\n{blob[:14000]}"
    )
    try:
        text, _, _ = llm_runtime.chat("answer", _SYSTEM, user)
        data = _parse_json(text)
        if data:
            return _normalize(data, samples, customer_brief)
        logger.warning("smart_understand: unparseable model output")
    except Exception as exc:  # noqa: BLE001
        logger.warning("smart_understand LLM failed: %s", exc)
    return _fallback(samples, user_hint, customer_brief)


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        # try strip markdown fences
        cleaned = re.sub(r"```(?:json)?", "", text).strip()
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s < 0:
            return None
        try:
            return json.loads(cleaned[s : e + 1])
        except json.JSONDecodeError:
            return None


def _slist(v: Any) -> list[str]:
    if isinstance(v, str):
        return [ln.strip() for ln in v.splitlines() if ln.strip()]
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _normalize(data: dict[str, Any], samples: list[dict[str, Any]],
               customer_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalise model output.

    `brief` on the result is the DERIVED reading of the data — never the
    customer's. The customer's own brief rides along untouched under
    `customer_brief` so no caller can confuse the two.
    """
    brief_in = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    brief = {
        "domain": str(brief_in.get("domain") or "").strip(),
        "aim": str(brief_in.get("aim") or "").strip(),
        "objectives": _slist(brief_in.get("objectives")),
        "scope": str(brief_in.get("scope") or "").strip(),
        "roles": _slist(brief_in.get("roles")),
        "questions": _slist(brief_in.get("questions")),
    }
    gp = data.get("graph_plan") if isinstance(data.get("graph_plan"), dict) else {}
    primary = gp.get("primary_types") if isinstance(gp.get("primary_types"), list) else []
    dims = gp.get("dimension_types") if isinstance(gp.get("dimension_types"), list) else []
    rels = gp.get("relationships") if isinstance(gp.get("relationships"), list) else []
    follow = data.get("follow_ups") if isinstance(data.get("follow_ups"), list) else []
    docs = data.get("suggested_documents") if isinstance(
        data.get("suggested_documents"), list) else []

    # Attach real column lists for UI validation
    col_map = {s["filename"]: s.get("columns") or [] for s in samples}
    return {
        "summary": str(data.get("summary") or "").strip(),
        "brief": brief,
        "graph_plan": {
            "primary_types": primary,
            "dimension_types": dims,
            "relationships": rels,
            "outcomes": _slist(gp.get("outcomes")),
        },
        "follow_ups": follow,
        "suggested_documents": docs,
        "source_columns": col_map,
        "customer_brief": dict(customer_brief or {}),
        # The server's own verdict — the UI must not re-derive "is this
        # brief real?", or it can disagree with the promote rule and tell
        # the user their brief is authoritative while it gets overwritten.
        "customer_brief_populated": brief_is_populated(customer_brief),
        "divergences": _slist(data.get("divergences")),
        "gaps": _slist(data.get("gaps")),
        "fallback": False,
    }


def _fallback(samples: list[dict[str, Any]], hint: str,
              customer_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    """Heuristic plan when LLM is offline — still multi-type when columns allow."""
    names = [s.get("filename") or "file" for s in samples]
    tab = next((s for s in samples if s.get("kind") == "tabular"), None)
    cols = (tab or {}).get("columns") or []
    stem = Path(names[0]).stem.replace("_", " ").title().replace(" ", "") or "Record"
    # Bank-ish heuristic
    lower = {c.lower(): c for c in cols}
    desc = lower.get("description") or lower.get("payee") or lower.get("memo") or lower.get("narration")
    cat = lower.get("category") or lower.get("type") or lower.get("mcc")
    date = lower.get("date") or lower.get("posted") or lower.get("transaction date")
    amt = lower.get("amount") or lower.get("debit") or lower.get("credit")
    primary_keys = [k for k in (date, amt, desc) if k] or (cols[:2] if cols else ["name"])
    dims: list[dict[str, Any]] = []
    rels: list[dict[str, Any]] = []
    if desc:
        dims.append({"name": "Merchant", "source_column": desc, "role": "dimension",
                     "from_type": stem if "bank" in stem.lower() or "trans" in stem.lower()
                     else "Transaction"})
        ptype = "BankTransaction" if any(
            x in " ".join(names).lower() for x in ("bank", "fsb", "check", "trans")
        ) else stem
        dims[-1]["from_type"] = ptype
        rels.append({"name": "AT_MERCHANT", "from": ptype, "to": "Merchant",
                     "via_column": desc})
    else:
        ptype = stem
    if cat:
        dims.append({"name": "Category", "source_column": cat, "role": "dimension",
                     "from_type": ptype})
        rels.append({"name": "IN_CATEGORY", "from": ptype, "to": "Category",
                     "via_column": cat})
    cb = customer_brief or {}
    # Offline, the customer's own words beat any filename heuristic.
    domain = str(cb.get("domain") or "").strip() or (
        "Personal banking" if "bank" in " ".join(names).lower() or desc
        else (hint or "Uploaded data"))
    brief = {
        "domain": domain,
        "aim": "Build a knowledge graph so questions about entities and links "
               "in this data can be answered with provenance.",
        "objectives": [
            "Identify the main record type from each file",
            "Link dimensions (merchants, categories, people) when columns allow",
            "Support proof questions from the brief",
        ],
        "scope": f"IN: types derived from {', '.join(names)}. OUT: unrelated domains.",
        "roles": ["Analyst — what patterns exist?", "Owner — what needs cleanup?"],
        "questions": [
            "What are the main entity types?",
            "Which values repeat most in key columns?",
            "How do records relate across types?",
        ],
    }
    if desc:
        brief["questions"] = [
            "Which merchants appear most often?",
            "How do transactions distribute by category?",
            "What is the total activity over time?",
        ]
    # Customer-stated aim / proof questions survive the heuristic path too.
    if str(cb.get("aim") or "").strip():
        brief["aim"] = str(cb["aim"]).strip()
    if cb.get("questions"):
        brief["questions"] = [str(q).strip() for q in cb["questions"]
                              if str(q).strip()]
    if cb.get("objectives"):
        brief["objectives"] = [str(o).strip() for o in cb["objectives"]
                               if str(o).strip()]
    return {
        "summary": (
            f"Offline/heuristic understand for {', '.join(names)}. "
            "Configure an answer model in Settings for a richer plan."
        ),
        "brief": brief,
        "graph_plan": {
            "primary_types": [{
                "name": ptype if desc else stem,
                "match_keys": primary_keys,
                "role": "row",
                "source_file": names[0],
            }],
            "dimension_types": dims,
            "relationships": rels,
            "outcomes": ["Browse entities on Data", "Ask grounded questions"],
        },
        "follow_ups": [{
            "id": "goal",
            "question": "What outcome do you want from this graph? "
                        "(e.g. travel cities, spend by merchant, churn risk)",
            "why": "Steers dimensions and proof questions",
        }],
        "suggested_documents": [
            {"what": "Lookup or reference list (merchants, cities, products)",
             "why": "Sharpens links beyond free-text columns"},
        ],
        "source_columns": {s["filename"]: s.get("columns") or [] for s in samples},
        "customer_brief": dict(cb),
        "customer_brief_populated": brief_is_populated(cb),
        "divergences": [],
        "gaps": [],
        "fallback": True,
    }


def _empty_result(msg: str) -> dict[str, Any]:
    return {
        "summary": msg,
        "brief": {"domain": "", "aim": "", "objectives": [], "scope": "",
                  "roles": [], "questions": []},
        "graph_plan": {"primary_types": [], "dimension_types": [],
                       "relationships": [], "outcomes": []},
        "follow_ups": [],
        "suggested_documents": [],
        "source_columns": {},
        "customer_brief": {},
        "customer_brief_populated": False,
        "divergences": [],
        "gaps": [],
        "fallback": True,
    }


def primary_type_and_keys(plan: dict[str, Any] | None,
                          filename: str = "") -> tuple[str, list[str]]:
    """Pick ontology_type + match_keys for a file from graph_plan."""
    plan = plan or {}
    primaries = plan.get("primary_types") or []
    if filename:
        for p in primaries:
            if not isinstance(p, dict):
                continue
            sf = str(p.get("source_file") or "")
            if sf and Path(sf).name == Path(filename).name:
                name = str(p.get("name") or "Record")
                keys = [str(k) for k in (p.get("match_keys") or []) if k]
                return name, keys or ["name"]
    if primaries and isinstance(primaries[0], dict):
        p = primaries[0]
        name = str(p.get("name") or "Record")
        keys = [str(k) for k in (p.get("match_keys") or []) if k]
        return name, keys or ["name"]
    return "Record", ["name"]
