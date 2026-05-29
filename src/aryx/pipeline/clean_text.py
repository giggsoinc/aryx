"""Text normalization and structure-aware chunking for document sources (Inc 8)."""
from __future__ import annotations

import re
import unicodedata

from aryx.models import DocumentChunk, SourceRef

_DEHYPHEN = re.compile(r"-\n(\S)")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _DEHYPHEN.sub(r"\1", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def chunk_pages(
    pages: list[tuple[int | None, str]],
    source: SourceRef,
    doc_id: str,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> list[DocumentChunk]:
    """Split page/slide texts into overlapping character-based chunks.

    Args:
        pages: Sequence of (page_num, raw_text) pairs from a document connector.
        source: Provenance reference for the source document.
        doc_id: Content hash of the source file.
        chunk_size: Target chunk length in characters.
        overlap: Character overlap between adjacent chunks (prevents boundary drops).

    Returns:
        Ordered list of DocumentChunk with char offsets relative to the normalized page.
    """
    chunks: list[DocumentChunk] = []
    chunk_index = 0
    for page_num, raw_text in pages:
        text = _normalize(raw_text)
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append(DocumentChunk(
                doc_id=doc_id,
                chunk_index=chunk_index,
                page_slide=page_num,
                text=chunk_text,
                char_start=start,
                char_end=end,
                source=source,
            ))
            chunk_index += 1
            if end == len(text):
                break
            start = end - overlap
    return chunks
