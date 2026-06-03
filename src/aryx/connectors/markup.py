"""XML / HTML document connector: stdlib-only text extraction (Inc 8+)."""
from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class MarkupConnector:
    """Extract plain text from .xml / .html / .htm using only the standard library."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def extract_pages(self) -> Iterator[tuple[None, str]]:
        """Yield a single (None, text) tuple — markup has no natural page breaks."""
        suffix = self._path.suffix.lower()
        raw = self._path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".xml":
            yield None, _extract_xml(raw)
        else:
            yield None, _extract_html(raw)

    def close(self) -> None:
        pass


def _extract_xml(raw: str) -> str:
    """Flatten an XML document into one text blob keyed by element path."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.warning("xml parse failed, falling back to regex strip: %s", exc)
        return re.sub(r"<[^>]+>", " ", raw)
    lines: list[str] = []
    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1]
        text = (elem.text or "").strip()
        if text:
            lines.append(f"{tag}: {text}")
        for attr, val in elem.attrib.items():
            val_s = (val or "").strip()
            if val_s:
                lines.append(f"{tag}.{attr}: {val_s}")
    return "\n".join(lines)


class _HtmlText(HTMLParser):
    """Drop <script>/<style> content; collect inner text."""

    _SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = data.strip()
        if cleaned:
            self._chunks.append(cleaned)

    def text(self) -> str:
        return "\n".join(self._chunks)


def _extract_html(raw: str) -> str:
    parser = _HtmlText()
    try:
        parser.feed(raw)
    except Exception as exc:
        logger.warning("html parse error: %s", exc)
    return parser.text()
