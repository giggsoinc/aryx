"""REST API ingest preview — fetch the endpoint, count records, return sample.

Full pipeline integration (entity extraction, resolution, projection) is the
next-step build; for the demo we surface a working fetch + sample so the
customer can see Aryx pulling their REST source.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.connectors.rest_api import RestApiConnector

logger = logging.getLogger(__name__)


class RestPreviewRequest(BaseModel):
    """Body for /ingest/rest/preview."""

    workspace_id: int = 1
    url: str
    headers: dict[str, str] = {}
    record_path: str = ""
    page_param: str = ""
    next_page_path: str = ""
    context: str = ""


def rest_ingest_router() -> APIRouter:
    """Build the /ingest/rest router."""
    router = APIRouter(prefix="/ingest/rest")

    @router.post("/preview")
    def preview(req: RestPreviewRequest) -> dict[str, Any]:
        """Fetch the URL and return the first 10 records + count."""
        try:
            conn = RestApiConnector(
                url=req.url, headers=req.headers,
                record_path=req.record_path,
                page_param=req.page_param,
                next_page_path=req.next_page_path,
                max_pages=1,
            )
            recs = list(conn.extract())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"REST fetch failed: {exc}") from exc
        return {
            "count": len(recs),
            "sample": [r.payload for r in recs[:10]],
            "message": ("Preview only — full ingest pipeline integration "
                        "ships in the next build."),
        }

    return router
