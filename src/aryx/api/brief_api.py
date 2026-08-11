"""Brief drafting API — turn a seed sentence + optional doc text into a brief.

Stateless: it drafts and returns the 5-field brief; the UI lets the user
edit it, then persists via the existing workspace brief PATCH. Document
text is extracted client-side (UI) and posted as plain text here.
"""
from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from aryx.api.admin_api import _local_broker
from aryx.brief_draft import draft_from_text

logger = logging.getLogger(__name__)

# Extensions the briefing doc-reader accepts. Text is extracted only —
# nothing is chunked, embedded, or landed in the data store.
_BRIEF_DOC_EXTS = {".pdf", ".docx", ".doc", ".rtf", ".pptx", ".ppt", ".txt", ".md"}
_BRIEF_DOC_MAX_BYTES = 20 * 1024 * 1024
_BRIEF_DOC_MAX_CHARS = 12000


def _extract_doc_text(data: bytes, filename: str) -> str:
    """Plain text from an uploaded briefing document, capped for the LLM."""
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md"}:
        return data.decode("utf-8", "ignore")[:_BRIEF_DOC_MAX_CHARS]
    tmp = NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        path = Path(tmp.name)
        if ext == ".pdf":
            from aryx.connectors.pdf import PdfConnector
            conn: Any = PdfConnector(path)
        elif ext in {".docx", ".doc", ".rtf"}:
            from aryx.connectors.docx import DocxConnector
            conn = DocxConnector(path)
        else:  # .pptx / .ppt
            from aryx.connectors.pptx import PptxConnector
            conn = PptxConnector(path)
        try:
            parts: list[str] = []
            total = 0
            for _page, text in conn.extract_pages():
                if text:
                    parts.append(text)
                    total += len(text)
                if total >= _BRIEF_DOC_MAX_CHARS:
                    break
            return "\n\n".join(parts)[:_BRIEF_DOC_MAX_CHARS]
        finally:
            conn.close()
    finally:
        path = Path(tmp.name)
        if path.exists():
            path.unlink()


class DraftBriefRequest(BaseModel):
    """Seed sentence and/or extracted document text to draft a brief from."""

    seed: str = ""
    doc_text: str = ""
    workspace_id: int = 1


def brief_router() -> APIRouter:
    """Build the /admin/workspaces brief-drafting router."""
    router = APIRouter(prefix="/admin/workspaces")

    @router.post("/{workspace_id}/draft-brief")
    def draft_brief(workspace_id: int,
                    req: DraftBriefRequest) -> dict[str, Any]:
        """Draft a 5-field brief from a seed sentence and/or document text."""
        brief = draft_from_text(_local_broker(), req.seed, req.doc_text)
        logger.info("brief drafted ws=%s seed=%d doc=%d", workspace_id,
                    len(req.seed), len(req.doc_text))
        return {"workspace_id": workspace_id, "brief": brief}

    @router.post("/{workspace_id}/brief-doc-text")
    async def brief_doc_text(workspace_id: int,
                             file: UploadFile) -> dict[str, Any]:
        """Extract plain text from one briefing document (PDF/DOC/PPT/…).

        Read-only helper for the Brief cruise-control step — the document
        is never ingested as data.
        """
        filename = file.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in _BRIEF_DOC_EXTS:
            raise HTTPException(
                415, f"unsupported type '{ext}' — accepted: "
                     f"{', '.join(sorted(_BRIEF_DOC_EXTS))}")
        data = await file.read()
        if len(data) > _BRIEF_DOC_MAX_BYTES:
            raise HTTPException(413, "file exceeds 20 MB limit")
        try:
            text = _extract_doc_text(data, filename)
        except Exception as exc:  # noqa: BLE001 — surface as a clean 422
            logger.warning("brief doc extract failed file=%s: %s",
                           filename, exc)
            raise HTTPException(422, f"could not read '{filename}': {exc}")
        logger.info("brief doc extracted ws=%s file=%s chars=%d",
                    workspace_id, filename, len(text))
        return {"workspace_id": workspace_id, "filename": filename,
                "chars": len(text), "text": text}

    return router
