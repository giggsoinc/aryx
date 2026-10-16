"""Corrections API — humans point Aryx in the right direction.

Every correction does two things, atomically from the user's view:
1. fixes the data NOW (RDB mutation, then a full graph re-project — the
   graph is a rebuildable projection, so re-projecting is the honest way
   to keep it consistent), and
2. records a standing rule (aryx_correction) that is replayed into every
   future ingest: suppressions and retypes feed the extraction context,
   pinned/forbidden links are enforced after the relate stage.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.graph.falkor_store import FalkorStore
from aryx.pipeline.enrich import _build_type_ancestors
from aryx.project import project_graph
from aryx.queries import load
from aryx.store.entity_store import EntityStore
from aryx.store.relationship_repoint import repoint_relationships_safely
from aryx.workspaces import ws_graph

logger = logging.getLogger(__name__)

_KINDS = {"retype", "remove", "link", "unlink", "merge", "rename_type"}


class CorrectionRequest(BaseModel):
    """One human correction. Fields used depend on kind."""

    kind: str
    entity_id: int = 0
    target_id: int = 0
    name: str = ""          # relationship name (link) or new type (retype)
    type_name: str = ""     # rename_type: the EXISTING type to rename


class ChatCorrection(BaseModel):
    """A plain-language correction utterance from the graph chat dock."""

    text: str
    selected_entity_id: int = 0


def _db() -> psycopg.Connection:
    return psycopg.connect(get_settings().rdb_dsn, autocommit=True)


def _entity(cur: psycopg.Cursor, ws: int, eid: int) -> tuple[int, str, Any]:
    cur.execute(load("select_entity_brief"), (ws, eid))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"entity {eid} not found in workspace {ws}")
    return row


def _display(attrs: Any) -> str:
    if isinstance(attrs, dict):
        return str(attrs.get("name") or attrs.get("title") or "")[:200]
    return ""


def _t(entity_id: int, roster: list) -> str:
    """Type of an entity in the chat roster ('' if unknown)."""
    for eid, _name, typ in roster:
        if eid == entity_id:
            return typ
    return ""


def _reproject(workspace_id: int) -> dict[str, int]:
    settings = get_settings()
    estore = EntityStore(settings.rdb_dsn, workspace_id)
    try:
        return project_graph(
            estore, FalkorStore(settings.graph_url, ws_graph(workspace_id)),
            type_ancestors=_build_type_ancestors(settings.rdb_dsn),
            workspace_id=workspace_id)
    finally:
        estore.close()


def corrections_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/workspaces/{workspace_id}/corrections")
    def add_correction(workspace_id: int,
                       req: CorrectionRequest) -> dict[str, Any]:
        """Apply a correction now and record it as a standing rule."""
        return _apply_correction(workspace_id, req)

    @router.post("/workspaces/{workspace_id}/corrections/chat")
    def correction_chat(workspace_id: int, body: ChatCorrection) -> dict[str, Any]:
        """Plain-language corrections: parse intent, resolve names, apply.

        WRITE-ONLY surface — completely separate from Ask. The LLM only
        classifies the utterance into a correction; every actual edit goes
        through the same audited _apply_correction path the buttons use.
        """
        text = body.text.strip()
        if not text:
            raise HTTPException(400, "empty message")
        conn = _db()
        try:
            with conn.cursor() as cur:
                cur.execute(load("select_entities_for_chat"), (workspace_id,))
                ents = [(int(r[0]), str(r[1]), _display(r[2])) for r in cur.fetchall()]
        finally:
            conn.close()
        roster = [(eid, name, typ) for eid, typ, name in ents if name]
        selected = next((r for r in roster if r[0] == body.selected_entity_id), None)
        conn = _db()
        try:
            with conn.cursor() as cur:
                cur.execute(load("select_type_names"), (workspace_id,))
                type_names = [str(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()

        from aryx.api.admin_api import _local_broker
        from aryx.llm import complete_json
        system = (
            "You translate ONE user instruction about a knowledge graph into "
            "ONE correction. Respond with EXACTLY this JSON shape: "
            '{"kind": "retype|merge|link|unlink|remove|rename_type|none", '
            '"subject": "", "target": "", "name": ""}.\n'
            "Rules:\n"
            "- retype: subject = an ENTITY name, name = its correct type.\n"
            "- rename_type: subject = an existing TYPE name, name = the new "
            "type name. Use this whenever the subject matches the type list.\n"
            "- merge/link/unlink: subject and target are ENTITY names.\n"
            "- none: only for questions or non-corrections.\n"
            "Examples:\n"
            '  "Maria is a HumanRole" → {"kind":"retype","subject":"Maria",'
            '"target":"","name":"HumanRole"}\n'
            '  "AI Security Governance is GREaaS" (subject is a TYPE) → '
            '{"kind":"rename_type","subject":"AI Security Governance",'
            '"target":"","name":"GREaaS"}\n'
            '  "link T-100 to Maria as resolved" → {"kind":"link",'
            '"subject":"T-100","target":"Maria","name":"resolved"}\n'
            + (f'The user currently has "{selected[1]}" selected — use it as '
               f"subject when they say this/it.\n" if selected else "")
            + "TYPE list: " + "; ".join(type_names[:80]) + "\n"
            + "ENTITY roster: "
            + "; ".join(f"{n} [{t}]" for _e, n, t in roster[:250]))
        parsed = complete_json(_local_broker(), "cheap", system, text, {
            "kind": "string", "subject": "string",
            "target": "string", "name": "string"})
        # llm_normalize may rename "kind" to "type" — accept both.
        kind = str(parsed.get("kind") or parsed.get("type")
                   or "none").strip().lower()
        subject_raw = str(parsed.get("subject") or "").strip()
        # The model sometimes calls a type-rename a retype — correct it
        # deterministically: a subject matching a TYPE name is a type op.
        lower_types = {t.lower(): t for t in type_names}
        if kind in ("retype", "rename_type") and subject_raw.lower() in lower_types:
            kind = "rename_type"
        if kind not in _KINDS:
            return {"status": "none",
                    "message": "I read that as a question, not a correction — "
                               "for questions use Ask. Corrections I can do: "
                               "retype an entity, rename a type, merge "
                               "duplicates, link/unlink two entities, or "
                               "remove junk. Try naming the exact entity or "
                               "type you want changed."}

        if kind == "rename_type":
            old = lower_types.get(subject_raw.lower())
            new = str(parsed.get("name") or "").strip()
            if not old or not new:
                return {"status": "unclear",
                        "message": "Which type should become what? "
                                   "Say: rename type <old> to <new>."}
            return {"status": "proposal",
                    "message": f'Rename type “{old}” → “{new}” (all its '
                               "entities move with it). Apply?",
                    "action": {"kind": "rename_type", "type_name": old,
                               "name": new}}

        def _resolve(name: str) -> tuple[int, str] | list[str] | None:
            n = name.strip().lower()
            if not n:
                return None
            exact = [r for r in roster if r[1].lower() == n]
            if len(exact) == 1:
                return exact[0][0], exact[0][1]
            part = [r for r in roster if n in r[1].lower()]
            if len(part) == 1:
                return part[0][0], part[0][1]
            if len(part) > 1:
                return [r[1] for r in part[:5]]
            return None

        subj = _resolve(str(parsed.get("subject") or "")) or (
            (selected[0], selected[1]) if selected else None)
        if subj is None:
            return {"status": "unclear",
                    "message": f"I couldn't find \"{parsed.get('subject')}\" "
                               "in this workspace — click the entity or use "
                               "its exact name."}
        if isinstance(subj, list):
            return {"status": "ambiguous",
                    "message": "Which one? " + " · ".join(subj)}
        tgt: tuple[int, str] | None = None
        if kind in ("merge", "link", "unlink"):
            t = _resolve(str(parsed.get("target") or ""))
            if t is None or isinstance(t, list):
                opts = " · ".join(t) if isinstance(t, list) else ""
                return {"status": "ambiguous" if opts else "unclear",
                        "message": (f"Which target? {opts}" if opts else
                                    "Name the second entity exactly.")}
            tgt = t
        name = str(parsed.get("name") or "").strip()
        if kind == "retype" and not name:
            return {"status": "unclear",
                    "message": f'Retype “{subj[1]}” to what? Name the type.'}
        if kind == "link" and not name:
            name = "related_to"
        summary = {
            "retype": f'Retype “{subj[1]}” ({_t(subj[0], roster)}) → “{name}”.',
            "remove": f'Remove “{subj[1]}” and never extract it again.',
            "link": f'Link “{subj[1]}” —{name}→ “{tgt[1] if tgt else ""}”.',
            "unlink": f'Unlink “{subj[1]}” and “{tgt[1] if tgt else ""}” — '
                      "and never relate them again.",
            "merge": f'Merge “{subj[1]}” into “{tgt[1] if tgt else ""}” '
                     "(they are the same thing).",
        }[kind]
        return {"status": "proposal",
                "message": summary + " Apply?",
                "action": {"kind": kind, "entity_id": subj[0],
                           "target_id": tgt[0] if tgt else 0, "name": name}}

    @router.get("/workspaces/{workspace_id}/corrections")
    def list_corrections(workspace_id: int) -> list[dict[str, Any]]:
        conn = _db()
        try:
            with conn.cursor() as cur:
                cur.execute(load("select_corrections"), (workspace_id,))
                cols = ["id", "kind", "subject", "object", "detail", "created_at"]
                return [dict(zip(cols, (*r[:5], str(r[5]))))
                        for r in cur.fetchall()]
        finally:
            conn.close()

    @router.delete("/corrections/{correction_id}")
    def delete_correction(correction_id: int) -> dict[str, str]:
        conn = _db()
        try:
            with conn.cursor() as cur:
                cur.execute(load("delete_correction"), (correction_id,))
        finally:
            conn.close()
        return {"status": "deleted"}

    return router


def _apply_correction(workspace_id: int,
                      req: CorrectionRequest) -> dict[str, Any]:
    """Shared apply path for buttons AND chat — one audit trail."""
    if True:  # keep original indentation block below
        kind = req.kind.strip().lower()
        if kind not in _KINDS:
            raise HTTPException(400, f"kind must be one of {sorted(_KINDS)}")
        if kind == "rename_type":
            if not req.type_name or not req.name:
                raise HTTPException(400, "rename_type needs type_name + name")
            conn = _db()
            try:
                with conn.cursor() as cur:
                    cur.execute(load("rename_ontology_type"),
                                (req.name, workspace_id, req.type_name))
                    if cur.fetchone() is None:
                        raise HTTPException(
                            404, f"type '{req.type_name}' not found")
                    cur.execute(load("retype_entities_by_type"),
                                (req.name, workspace_id, req.type_name))
                    moved = cur.rowcount
                    cur.execute(load("insert_correction"),
                                (workspace_id, "rename_type", req.type_name,
                                 req.name, f"{moved} entities moved"))
                    rule_id, created = cur.fetchone()
            finally:
                conn.close()
            counts = _reproject(workspace_id)
            return {"id": rule_id, "kind": "rename_type",
                    "subject": req.type_name, "object": req.name,
                    "detail": f"{moved} entities moved",
                    "created_at": str(created), "graph": counts}
        conn = _db()
        try:
            with conn.cursor() as cur:
                _id, cur_type, attrs = _entity(cur, workspace_id, req.entity_id)
                subject = _display(attrs) or f"#{req.entity_id}"
                obj, detail = "", ""

                if kind == "retype":
                    if not req.name:
                        raise HTTPException(400, "retype needs name=<new type>")
                    cur.execute(load("retype_entity"),
                                (req.name, workspace_id, req.entity_id))
                    obj, detail = req.name, f"was {cur_type}"

                elif kind == "remove":
                    cur.execute(load("delete_relationships_by_entity"),
                                (workspace_id, req.entity_id, req.entity_id))
                    cur.execute(load("delete_members_by_entity"),
                                (workspace_id, req.entity_id))
                    cur.execute(load("delete_entity_by_id"),
                                (workspace_id, req.entity_id))
                    obj, detail = cur_type, "suppressed — never extract again"

                elif kind in ("link", "unlink", "merge"):
                    _tid, tgt_type, tattrs = _entity(cur, workspace_id,
                                                     req.target_id)
                    obj = _display(tattrs) or f"#{req.target_id}"
                    if kind == "link":
                        if not req.name:
                            raise HTTPException(400, "link needs name=<relationship>")
                        cur.execute(load("insert_relationship_manual"),
                                    (workspace_id, req.entity_id,
                                     req.target_id, req.name))
                        detail = req.name
                    elif kind == "unlink":
                        cur.execute(load("delete_relationship_pair"),
                                    (workspace_id, req.entity_id, req.target_id,
                                     req.target_id, req.entity_id))
                        detail = "forbidden — never relate again"
                    else:  # merge: entity_id absorbed INTO target_id
                        repoint_relationships_safely(
                            cur, workspace_id, req.entity_id, req.target_id)
                        cur.execute(load("repoint_members"),
                                    (req.target_id, workspace_id, req.entity_id))
                        cur.execute(load("delete_entity_by_id"),
                                    (workspace_id, req.entity_id))
                        detail = f"alias of {obj}"

                rule_kind = {"retype": "retype", "remove": "suppress",
                             "link": "pin_link", "unlink": "forbid_link",
                             "merge": "alias"}[kind]
                cur.execute(load("insert_correction"),
                            (workspace_id, rule_kind, subject, obj, detail))
                rule_id, created = cur.fetchone()
        finally:
            conn.close()
        counts = _reproject(workspace_id)
        logger.info("correction applied ws=%s kind=%s subject=%s",
                    workspace_id, kind, subject)
        return {"id": rule_id, "kind": rule_kind, "subject": subject,
                "object": obj, "detail": detail,
                "created_at": str(created), "graph": counts}


def corrections_digest(workspace_id: int) -> str:
    """Standing rules rendered for the extraction prompt (replay path)."""
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(load("select_corrections"), (workspace_id,))
            rows = cur.fetchall()
    except Exception:  # noqa: BLE001 — steering is best-effort
        return ""
    finally:
        conn.close()
    lines = []
    for _id, kind, subject, obj, _detail, _ts in rows:
        if kind == "rename_type":
            lines.append(f'The type "{subject}" is now called "{obj}" — '
                         f'always use "{obj}".')
        elif kind == "retype":
            lines.append(f'"{subject}" must be typed as {obj}.')
        elif kind == "suppress":
            lines.append(f'Never extract "{subject}" — it is noise.')
        elif kind == "alias":
            lines.append(f'"{subject}" is the same entity as "{obj}".')
        elif kind == "pin_link":
            lines.append(f'"{subject}" is related to "{obj}".')
        elif kind == "forbid_link":
            lines.append(f'"{subject}" is NOT related to "{obj}".')
    return "\n".join(lines[:40])
