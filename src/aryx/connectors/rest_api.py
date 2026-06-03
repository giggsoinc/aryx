"""REST API source connector — fetch records from any JSON HTTP endpoint.

Supports static auth (Bearer / API-Key / Basic), pagination via a configurable
page-token field, and a JSON-path-lite (dotted) record selector. Each fetched
JSON object becomes one RawRecord. No third-party deps beyond stdlib.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

from aryx.connectors.base import Connector
from aryx.models import RawRecord, SourceRef

logger = logging.getLogger(__name__)


def _select(payload: Any, path: str) -> list[dict]:
    """Dotted-path selector → list of records. Empty path returns top-level list."""
    node: Any = payload
    if path:
        for part in path.split("."):
            if isinstance(node, dict):
                node = node.get(part)
            elif isinstance(node, list) and part.isdigit():
                node = node[int(part)] if int(part) < len(node) else None
            else:
                return []
    if node is None:
        return []
    if isinstance(node, list):
        return [r for r in node if isinstance(r, dict)]
    if isinstance(node, dict):
        return [node]
    return []


def _request(url: str, headers: dict[str, str], timeout: int = 30) -> Any:
    """One GET request, return parsed JSON."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class RestApiConnector(Connector):
    """Extract records from a paginated REST JSON endpoint."""

    def __init__(self, url: str, headers: dict[str, str] | None = None,
                 record_path: str = "", page_param: str = "",
                 next_page_path: str = "", max_pages: int = 20) -> None:
        """Configure the source.

        Args:
            url: Base endpoint URL.
            headers: Static headers, e.g. {"Authorization": "Bearer ..."}.
            record_path: Dotted path to the list of records inside the JSON.
            page_param: Query-string param for the page token (empty = no pagination).
            next_page_path: Dotted path inside the response for the next page token.
            max_pages: Hard safety cap.
        """
        self._url = url
        self._headers = headers or {}
        self._record_path = record_path
        self._page_param = page_param
        self._next_page_path = next_page_path
        self._max_pages = max(1, int(max_pages))

    def _next_url(self, current: str, payload: Any) -> str:
        """Compute the next-page URL or empty string if no more pages."""
        if not self._page_param or not self._next_page_path:
            return ""
        node: Any = payload
        for part in self._next_page_path.split("."):
            if isinstance(node, dict):
                node = node.get(part)
            else:
                return ""
        if not node:
            return ""
        sep = "&" if "?" in current else "?"
        return f"{current.split('?')[0]}?{self._page_param}={urllib.parse.quote(str(node))}"

    def extract(self) -> Iterator[RawRecord]:
        """Yield one RawRecord per JSON object across all pages."""
        url = self._url
        seen = 0
        for page in range(self._max_pages):
            try:
                payload = _request(url, self._headers)
            except Exception as exc:  # noqa: BLE001
                logger.error("rest fetch failed page=%d url=%s err=%s",
                             page, url, exc)
                return
            records = _select(payload, self._record_path)
            for rec in records:
                seen += 1
                yield RawRecord(
                    source=SourceRef(system="rest", dataset=self._url,
                                     record_id=str(rec.get("id", seen))),
                    payload=rec,
                )
            nxt = self._next_url(url, payload)
            if not nxt:
                return
            url = nxt
        logger.info("rest extracted records=%d pages=%d", seen, self._max_pages)
