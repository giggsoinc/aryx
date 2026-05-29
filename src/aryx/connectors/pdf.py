"""PDF document connector: text extraction + embedded image OCR (Inc 8)."""
from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfConnector:
    """Extracts text from PDF pages via pymupdf; OCRs embedded images via pytesseract."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def extract_pages(self) -> Iterator[tuple[int, str]]:
        """Yield (page_num, text) for every page, including OCR of embedded images."""
        import fitz  # pymupdf

        doc = fitz.open(str(self._path))
        try:
            for page_num, page in enumerate(doc, start=1):
                parts = [page.get_text()]
                for img_info in page.get_images(full=True):
                    ocr_text = _ocr_image_bytes(doc.extract_image(img_info[0])["image"])
                    if ocr_text:
                        parts.append(ocr_text)
                yield page_num, "\n".join(parts)
        finally:
            doc.close()

    def close(self) -> None:
        pass


def _ocr_image_bytes(img_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:
        logger.debug("ocr skipped: %s", exc)
        return ""
