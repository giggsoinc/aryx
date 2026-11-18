"""PPTX document connector: slide text, tables, notes + embedded image OCR (Inc 8)."""
from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from aryx.raven_log_config import log as raven_log

logger = logging.getLogger(__name__)


class UnsupportedDocumentError(ValueError):
    """The file is a document type we cannot read (clear, user-actionable message)."""


class PptxConnector:
    """Extracts text from PPTX slides via python-pptx; OCRs embedded images.

    Per slide it collects: text frames (recursing into group shapes), table
    cells, embedded-picture OCR and the speaker notes. One unreadable shape
    (broken/linked image, odd placeholder) is skipped and logged — it never
    aborts the whole deck.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _check_openxml(self) -> None:
        """python-pptx reads OpenXML (.pptx) only — legacy binary .ppt is not a zip."""
        if not zipfile.is_zipfile(self._path):
            raise UnsupportedDocumentError(
                "This is not an OpenXML .pptx file (legacy binary .ppt is not "
                "supported). Open it in PowerPoint and Save As .pptx, then re-upload.")

    def extract_pages(self) -> Iterator[tuple[int, str]]:
        """Yield (slide_num, text) for every slide, including OCR of embedded images."""
        from pptx import Presentation

        self._check_openxml()
        prs = Presentation(str(self._path))
        for slide_num, slide in enumerate(prs.slides, start=1):
            parts: list[str] = []
            _collect_shapes(slide.shapes, parts, slide_num)
            try:
                if slide.has_notes_slide:
                    notes = slide.notes_slide.notes_text_frame
                    if notes is not None and notes.text.strip():
                        parts.append(notes.text)
            except Exception as exc:  # noqa: BLE001 — notes are additive
                logger.warning("pptx slide=%d notes skipped: %s", slide_num, exc)
                raven_log("WARN", "pptx speaker notes skipped; deck ingest continues",
                          criticality="P4", service="aryx-api",
                          error_code="PPTX_NOTES_SKIPPED",
                          context={"slide": slide_num, "exception": type(exc).__name__,
                                   "stage": "Documents", "result": "skipped_element"})
            yield slide_num, "\n".join(parts)

    def close(self) -> None:
        pass


def _collect_shapes(shapes: Iterable, parts: list[str], slide_num: int) -> None:
    """Append text/table/OCR text for each shape; recurse into group shapes."""
    for shape in shapes:
        try:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                if shape.text_frame.text.strip():
                    parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            if hasattr(shape, "shapes"):  # GroupShape
                _collect_shapes(shape.shapes, parts, slide_num)
        except Exception as exc:  # noqa: BLE001 — one bad shape must not drop the deck
            logger.warning("pptx slide=%d shape text skipped: %s", slide_num, exc)
            raven_log("WARN", "pptx shape text skipped; deck ingest continues",
                      criticality="P4", service="aryx-api",
                      error_code="PPTX_SHAPE_SKIPPED",
                      context={"slide": slide_num, "exception": type(exc).__name__,
                               "stage": "Documents", "result": "skipped_element"})
        _ocr_picture(shape, parts, slide_num)


def _ocr_picture(shape, parts: list[str], slide_num: int) -> None:
    """OCR an embedded picture. `shape.image` raises for broken/linked pictures
    (KeyError/ValueError), and plain `hasattr` only swallows AttributeError."""
    try:
        if not hasattr(shape, "image"):
            return
        blob = shape.image.blob
    except Exception as exc:  # noqa: BLE001
        logger.warning("pptx slide=%d picture skipped: %s: %s",
                       slide_num, type(exc).__name__, exc)
        raven_log("WARN", "pptx picture unreadable; deck ingest continues without it",
                  criticality="P4", service="aryx-api",
                  error_code="PPTX_PICTURE_SKIPPED",
                  context={"slide": slide_num, "exception": type(exc).__name__,
                           "stage": "Documents", "result": "skipped_element"})
        return
    ocr_text = _ocr_image_bytes(blob)
    if ocr_text:
        parts.append(ocr_text)


def _ocr_image_bytes(img_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:
        logger.debug("ocr skipped: %s", exc)
        return ""
