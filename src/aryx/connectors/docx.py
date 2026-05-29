"""DOCX/RTF document connector: body text + embedded image OCR (Inc 8)."""
from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


class DocxConnector:
    """Extracts text from .docx files via python-docx and .rtf via striprtf."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def extract_pages(self) -> Iterator[tuple[None, str]]:
        """Yield a single (None, text) tuple — docx/rtf have no natural page breaks."""
        suffix = self._path.suffix.lower()
        if suffix == ".rtf":
            yield None, _extract_rtf(self._path)
        else:
            yield None, _extract_docx(self._path)

    def close(self) -> None:
        pass


def _extract_rtf(path: Path) -> str:
    from striprtf.striprtf import rtf_to_text
    raw = path.read_text(encoding="utf-8", errors="replace")
    return rtf_to_text(raw)


def _extract_docx(path: Path) -> str:
    import docx

    doc = docx.Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            try:
                img_bytes = rel.target_part.blob
                ocr_text = _ocr_image_bytes(img_bytes)
                if ocr_text:
                    parts.append(ocr_text)
            except Exception as exc:
                logger.debug("image rel skipped: %s", exc)
    return "\n".join(parts)


def _ocr_image_bytes(img_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:
        logger.debug("ocr skipped: %s", exc)
        return ""
