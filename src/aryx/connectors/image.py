"""Standalone image connector: OCR via pytesseract (Inc 8)."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}


class ImageConnector:
    """Runs pytesseract OCR on a standalone image file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def extract_pages(self) -> Iterator[tuple[None, str]]:
        """Yield a single (None, ocr_text) — images have no page structure."""
        import pytesseract
        from PIL import Image

        img = Image.open(str(self._path))
        text = pytesseract.image_to_string(img).strip()
        logger.info("ocr image path=%s chars=%d", self._path.name, len(text))
        yield None, text

    def close(self) -> None:
        pass
