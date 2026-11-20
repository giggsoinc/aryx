"""PDF document connector: text extraction + embedded image OCR (Inc 8)."""
from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfConnector:
    """Extracts text from PDF pages via pymupdf; OCRs embedded images via pytesseract.

    ``skip_tables`` leaves out the text inside ruled tables. Set it when those
    tables are ingested as rows (connectors.doc_tables), so each cell is not
    also fed to the LLM a second time as prose.
    """

    def __init__(self, path: Path, skip_tables: bool = False, ocr=None) -> None:
        self._path = path
        self._skip_tables = skip_tables
        self._ocr = ocr

    def extract_pages(self) -> Iterator[tuple[int, str]]:
        """Yield (page_num, text) for every page, including OCR of embedded images."""
        import fitz  # pymupdf

        doc = fitz.open(str(self._path))
        try:
            if self._ocr is not None:
                from aryx.connectors.ocr_vision import doc_key, page_is_blank, split_markdown_tables

                key = doc_key(self._path.read_bytes())
            for page_num, page in enumerate(doc, start=1):
                parts = [_page_text(page, self._skip_tables)]
                if self._ocr is not None and page_is_blank(page):
                    # A scan: the vision model reads the page picture. Tables
                    # already ingested as rows are left out of the text.
                    scanned = self._ocr.text(key, page_num, page)
                    if self._skip_tables:
                        scanned = split_markdown_tables(scanned)[0]
                    if scanned:
                        parts.append(scanned)
                for img_info in page.get_images(full=True):
                    ocr_text = _ocr_image_bytes(doc.extract_image(img_info[0])["image"])
                    if ocr_text:
                        parts.append(ocr_text)
                yield page_num, "\n".join(parts)
        finally:
            doc.close()

    def close(self) -> None:
        pass


def _page_text(page, skip_tables: bool) -> str:
    """Page text; with ``skip_tables`` the blocks inside table areas are dropped."""
    if not skip_tables:
        return page.get_text()
    from aryx.connectors.doc_tables import pdf_page_tables

    boxes = [bbox for bbox, _ in pdf_page_tables(page)]
    if not boxes:
        return page.get_text()
    kept = []
    for x0, y0, x1, y1, text, _no, kind in page.get_text("blocks"):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inside = any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)
        if kind == 0 and not inside:
            kept.append(text.rstrip())
    return "\n".join(kept)


def _ocr_image_bytes(img_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:
        logger.debug("ocr skipped: %s", exc)
        return ""
