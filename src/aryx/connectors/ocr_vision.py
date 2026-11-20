"""OCR for scanned PDF pages: a vision model reads the page picture.

A scanned PDF has no text layer, so text extraction returns nothing. Here each
text-less page is rendered to an image and a vision model (Gemini, through its
OpenAI-compatible endpoint) transcribes it, writing tables as markdown tables.
Those tables are read as rows exactly like ruled tables in a text PDF, so a scan
keeps its layout instead of becoming a blob of text.

OCR is OFF by default (``ARYX_OCR=auto`` turns it on). A page image cannot be PII-
screened the way text is, and it leaves the deployment for the LLM provider, so it
is an explicit choice. Only pages with no text are sent, at most
``ARYX_OCR_MAX_PAGES`` (default 30) per document.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from collections.abc import Callable

from aryx.connectors.doc_tables import DocTable, _to_table

logger = logging.getLogger(__name__)

BLANK_PAGE_CHARS = 20
_VISION_PROVIDERS = {"google", "gemini", "openai"}
_ON = {"auto", "on", "gemini", "1", "true", "yes"}

_PROMPT = (
    "Transcribe this scanned page exactly as it is written. Keep the reading "
    "order. Write every table as a markdown table with a header row and a "
    "separator row (| a | b |, | --- | --- |), one table row per line. Do not "
    "summarize, translate, explain or add anything. If the page has no readable "
    "text, reply with nothing."
)

_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def page_is_blank(page) -> bool:
    """True for a page with no text layer (a scan, or an image-only page)."""
    return len(page.get_text().strip()) < BLANK_PAGE_CHARS


def doc_key(data: bytes) -> str:
    """Identifies one document's pages in the OCR cache."""
    return hashlib.sha1(data).hexdigest()  # noqa: S324 - a cache key, not security


class PageOcr:
    """Transcribes blank pages once each (cached), within a page budget per document."""

    def __init__(self, transcribe: Callable[[bytes], str], max_pages: int = 30,
                 dpi: int = 150) -> None:
        self._transcribe = transcribe
        self._max_pages = max_pages
        self._dpi = dpi
        self._cache: dict[tuple[str, int], str] = {}
        self._used: dict[str, int] = {}
        self.errors: list[str] = []       # why pages could not be read, for the job error

    def text(self, key: str, page_no: int, page) -> str:
        """The page's transcription ("" when over budget or when the model fails)."""
        cached = self._cache.get((key, page_no))
        if cached is not None:
            return cached
        if self._used.get(key, 0) >= self._max_pages:
            if self._used.get(key) == self._max_pages:
                logger.warning("ocr: page budget of %d reached for this document - the "
                               "remaining scanned pages are skipped (ARYX_OCR_MAX_PAGES)",
                               self._max_pages)
                self._used[key] += 1                       # warn once
            return ""
        self._used[key] = self._used.get(key, 0) + 1
        try:
            png = page.get_pixmap(dpi=self._dpi).tobytes("png")
            text = _strip_fences(self._transcribe(png))
        except Exception as exc:  # noqa: BLE001 - a page that fails must not fail the file
            logger.warning("ocr failed page=%d (%s: %.120s)", page_no, type(exc).__name__, exc)
            self.errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
            text = ""
        logger.info("ocr page=%d chars=%d", page_no, len(text))
        self._cache[(key, page_no)] = text
        return text


def _strip_fences(text: str) -> str:
    """Drop a ```markdown fence the model sometimes wraps its answer in."""
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text)
    return re.sub(r"\n```\s*$", "", text).strip()


def split_markdown_tables(text: str) -> tuple[str, list[DocTable]]:
    """(text without its markdown tables, the tables as DocTables)."""
    lines = text.split("\n")
    kept: list[str] = []
    tables: list[DocTable] = []
    i = 0
    while i < len(lines):
        # a table is a pipe row followed by a ---|--- separator row
        if "|" in lines[i] and i + 1 < len(lines) and _SEPARATOR.match(lines[i + 1]) \
                and "-" in lines[i + 1]:
            block = [lines[i]]
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                block.append(lines[j])
                j += 1
            grid = [[c.strip() for c in row.strip().strip("|").split("|")] for row in block]
            table = _to_table(grid)
            if table is not None:
                tables.append(table)
                i = j
                continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept).strip(), tables


def _transcribe_with(endpoint: str, model: str, key: str, png: bytes) -> str:
    from aryx.llm_providers import post_json

    body = {
        "model": model, "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}},
        ]}],
    }
    out = post_json(endpoint.rstrip("/") + "/chat/completions", body,
                    {"Authorization": f"Bearer {key}"}, timeout=120)
    return out["choices"][0]["message"]["content"] or ""


def make_page_ocr(broker) -> PageOcr | None:
    """A PageOcr for the configured LLM provider, or None when OCR cannot run.

    None unless ARYX_OCR is turned on (it is off by default: page images leave the
    deployment and cannot be PII-screened), the provider has no vision endpoint we
    support (Ollama, Anthropic), or there is no API key - the upload then behaves as
    it always did (a text-less PDF ends with a clear "no readable text" message).
    """
    if os.environ.get("ARYX_OCR", "off").strip().lower() not in _ON:
        return None
    try:
        spec = broker.choose("cheap")
        provider = str(spec.provider).lower()
        key = broker.secrets.get(spec.api_key_ref) if spec.api_key_ref else None
    except Exception as exc:  # noqa: BLE001 - OCR is an extra, never a reason to fail
        logger.info("ocr unavailable: %s", exc)
        return None
    if provider not in _VISION_PROVIDERS or not key or not spec.endpoint:
        logger.info("ocr unavailable: provider=%s has no usable vision endpoint/key", provider)
        return None
    try:
        budget = int(os.environ.get("ARYX_OCR_MAX_PAGES", "30"))
    except ValueError:
        budget = 30
    endpoint, model = spec.endpoint, spec.name
    return PageOcr(lambda png: _transcribe_with(endpoint, model, key, png), max_pages=budget)
