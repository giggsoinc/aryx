"""Regression tests for the "user unable to ingest .pptx" bug (RCA in the PR).

Root causes covered:
  1. PptxConnector dropped group/table/notes text and crashed the whole deck on
     one unreadable picture; legacy .ppt died with a cryptic PackageNotFoundError.
  2. The per-document timeout was a no-op (`with ThreadPoolExecutor` blocks on
     exit), so a hang (e.g. runtime model download) froze the job.
  3. Failures were swallowed and reported as "language model returned nothing".
  4. The Docker image never baked in the PII spaCy model, so the FIRST upload
     triggered a ~400 MB runtime download inside the ingest.
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path

import pytest

pytest.importorskip("pptx")

from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402

from aryx.connectors import doc_router  # noqa: E402
from aryx.connectors.pptx import PptxConnector, UnsupportedDocumentError  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def _png() -> io.BytesIO:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, "PNG")
    buf.seek(0)
    return buf


def _text(path: Path) -> str:
    return "\n".join(t for _, t in PptxConnector(path).extract_pages())


def test_extracts_title_group_table_and_notes(tmp_path: Path) -> None:
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[5])
    s1.shapes.title.text = "TITLE-TEXT"
    s2 = prs.slides.add_slide(prs.slide_layouts[6])
    grp = s2.shapes.add_group_shape()
    grp.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text_frame.text = "GROUP-TEXT"
    s3 = prs.slides.add_slide(prs.slide_layouts[6])
    tbl = s3.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(2)).table
    tbl.cell(0, 0).text = "CELL-A"
    tbl.cell(1, 1).text = "CELL-B"
    s4 = prs.slides.add_slide(prs.slide_layouts[6])
    s4.notes_slide.notes_text_frame.text = "NOTES-TEXT"
    f = tmp_path / "deck.pptx"
    prs.save(str(f))

    out = _text(f)
    for needle in ("TITLE-TEXT", "GROUP-TEXT", "CELL-A", "CELL-B", "NOTES-TEXT"):
        assert needle in out, f"{needle} was silently dropped from the deck"


def test_unreadable_picture_does_not_abort_the_deck(tmp_path: Path) -> None:
    """`shape.image` raises KeyError for a dangling relationship; `hasattr`
    only swallows AttributeError, so this used to fail the entire upload."""
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "STILL-HERE"
    pic = s.shapes.add_picture(_png(), Inches(1), Inches(2))
    pic._element.blipFill.blip.set(_RELS, "rId999")
    f = tmp_path / "broken_pic.pptx"
    prs.save(str(f))

    assert "STILL-HERE" in _text(f)


def test_legacy_binary_ppt_fails_with_actionable_message(tmp_path: Path) -> None:
    f = tmp_path / "old.ppt"
    f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 1024)  # OLE2 header
    with pytest.raises(UnsupportedDocumentError, match="Save As .pptx"):
        list(PptxConnector(f).extract_pages())


def test_timeout_releases_the_batch_and_names_the_original_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung document must be abandoned at the timeout — not block the batch
    until the hung worker finishes — and be reported under the user's filename."""
    monkeypatch.setattr(doc_router, "_PER_DOC_TIMEOUT", 0.3)
    monkeypatch.setattr(doc_router, "ingest_document",
                        lambda *a, **k: time.sleep(3) or [])
    staged = tmp_path / "tmpab12cd.pptx"
    staged.write_bytes(b"x")
    conn = doc_router.DocumentRouterConnector(
        paths=[staged], system="document", broker=None, chunk_store=None,
        display_names={staged: "Quarterly Review.pptx"})

    started = time.monotonic()
    assert list(conn.extract()) == []
    assert time.monotonic() - started < 2.0, "timeout did not release the batch"
    assert conn.failures and conn.failures[0][0] == "Quarterly Review.pptx"
    assert "took longer than" in conn.failures[0][1]
    assert "ARYX_PER_DOC_TIMEOUT" in conn.failures[0][1]


def test_failure_is_recorded_with_reason_not_swallowed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "tmp999.ppt"
    f.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 64)
    conn = doc_router.DocumentRouterConnector(
        paths=[f], system="document", broker=None, chunk_store=None,
        display_names={f: "legacy deck.ppt"})
    assert list(conn.extract()) == []
    (name, reason), = conn.failures
    assert name == "legacy deck.ppt"
    assert "UnsupportedDocumentError" in reason and ".pptx" in reason


def test_dockerfile_bakes_the_spacy_model_the_pii_gate_uses() -> None:
    """The model pii.py pins must be installed at image build time, otherwise
    Presidio downloads it at first ingest. Fails if either side drifts."""
    pii_src = (_REPO_ROOT / "src/aryx/pipeline/pii.py").read_text(encoding="utf-8")
    model = re.search(r'_DEFAULT_SPACY_MODEL = "([\w]+)"', pii_src)
    assert model, "pii.py must pin an explicit default spaCy model"
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert f"spacy download {model.group(1)}" in dockerfile
    assert "tesseract-ocr" in dockerfile, "pytesseract needs the tesseract binary"
