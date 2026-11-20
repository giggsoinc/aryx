"""Scanned PDF pages are read by a vision model; tables on a scan stay tables."""
from __future__ import annotations

import fitz
import pytest

from aryx.connectors import ocr_vision
from aryx.connectors.doc_tables import extract_tables, tables_as_csv_files
from aryx.connectors.ocr_vision import PageOcr, make_page_ocr, split_markdown_tables
from aryx.connectors.pdf import PdfConnector

_SCAN_TEXT = """Staff list, scanned

| Emp ID | Name | Dept ID |
| --- | --- | --- |
| E001 | Arjun Mehta | D1 |
| E002 | Priya Nair | D1 |
| E003 | Rahul Iyer | D2 |

Arjun Mehta joined in 2019.
"""


def _blank_pdf(tmp_path, pages=1):
    """A PDF whose pages have no text layer at all - what a scan looks like."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(fitz.Rect(50, 50, 200, 120), color=(0, 0, 0))   # a picture, not text
    path = tmp_path / "scan.pdf"
    doc.save(str(path))
    return path


class _Fake:
    """A PageOcr transcriber that records its calls."""

    def __init__(self, text=_SCAN_TEXT):
        self.text, self.calls = text, 0

    def __call__(self, png: bytes) -> str:
        assert png[:4] == b"\x89PNG"               # a real page image is sent
        self.calls += 1
        return self.text


def test_markdown_tables_become_tables_and_the_rest_stays_text():
    text, tables = split_markdown_tables(_SCAN_TEXT)
    assert len(tables) == 1
    assert tables[0].header == ["Emp ID", "Name", "Dept ID"]
    assert [r[1] for r in tables[0].rows] == ["Arjun Mehta", "Priya Nair", "Rahul Iyer"]
    assert "Arjun Mehta joined in 2019." in text and "| E001" not in text


def test_text_without_a_table_is_returned_untouched():
    text, tables = split_markdown_tables("Just a paragraph\nwith | a pipe in it\nand more.")
    assert tables == [] and text.startswith("Just a paragraph")


def test_a_scanned_page_is_transcribed_and_its_table_is_read_as_rows(tmp_path):
    path = _blank_pdf(tmp_path)
    fake = _Fake()
    ocr = PageOcr(fake)
    tables = extract_tables(path.read_bytes(), ".pdf", ocr)
    assert len(tables) == 1 and len(tables[0].rows) == 3
    # the text pass reuses the cached transcription: the model is asked once per page
    pages = list(PdfConnector(path, skip_tables=True, ocr=ocr).extract_pages())
    assert fake.calls == 1
    assert "Arjun Mehta joined in 2019." in pages[0][1]
    assert "| E001" not in pages[0][1]                    # table rows are not repeated as text


def test_without_skip_tables_the_whole_transcription_is_text(tmp_path):
    path = _blank_pdf(tmp_path)
    pages = list(PdfConnector(path, ocr=PageOcr(_Fake())).extract_pages())
    assert "| E001 | Arjun Mehta | D1 |" in pages[0][1]


def test_a_pdf_with_a_text_layer_never_calls_the_model(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((60, 80), "This page already has a real text layer.")
    path = tmp_path / "text.pdf"
    doc.save(str(path))
    fake = _Fake()
    pages = list(PdfConnector(path, ocr=PageOcr(fake)).extract_pages())
    assert fake.calls == 0 and "real text layer" in pages[0][1]


def test_the_page_budget_stops_a_huge_scan_from_costing_without_limit(tmp_path, caplog):
    path = _blank_pdf(tmp_path, pages=5)
    fake = _Fake("page text")
    pages = list(PdfConnector(path, ocr=PageOcr(fake, max_pages=2)).extract_pages())
    assert fake.calls == 2                                # pages 3-5 were not sent
    assert [bool(t.strip()) for _, t in pages] == [True, True, False, False, False]
    assert sum("page budget" in r.message for r in caplog.records) == 1


def test_a_page_the_model_fails_on_does_not_fail_the_document(tmp_path):
    path = _blank_pdf(tmp_path, pages=2)
    seen = {"n": 0}

    def flaky(png):
        seen["n"] += 1
        if seen["n"] == 1:
            raise TimeoutError("The read operation timed out")
        return "second page text"

    pages = list(PdfConnector(path, ocr=PageOcr(flaky)).extract_pages())
    assert pages[0][1].strip() == "" and "second page text" in pages[1][1]


def test_code_fences_around_the_answer_are_removed():
    assert ocr_vision._strip_fences("```markdown\n| a | b |\n| - | - |\n```") == "| a | b |\n| - | - |"
    assert ocr_vision._strip_fences("plain") == "plain"


def test_the_whole_upload_path_turns_a_scan_into_csv_rows(tmp_path):
    path = _blank_pdf(tmp_path)
    files, tabled = tables_as_csv_files([(path.read_bytes(), "scan.pdf")], ocr=PageOcr(_Fake()))
    assert tabled == {"scan.pdf"} and len(files) == 1
    csv_text = files[0][0].decode()
    assert csv_text.splitlines()[0] == "Emp ID,Name,Dept ID" and "E003,Rahul Iyer,D2" in csv_text


# ---- when OCR is available -------------------------------------------------------

class _Spec:
    def __init__(self, provider="google", key_ref="k", endpoint="https://example.test/v1beta/openai"):
        self.provider, self.api_key_ref, self.endpoint, self.name = provider, key_ref, endpoint, "gemini-2.5-flash"


class _Broker:
    def __init__(self, spec, key="secret"):
        self._spec = spec
        self.secrets = type("S", (), {"get": staticmethod(lambda _r: key)})()

    def choose(self, _tier):
        return self._spec


def test_ocr_is_off_by_default_because_page_images_leave_the_deployment(monkeypatch):
    """Review #56: a page image cannot be PII-screened like text, so it is opt-in."""
    monkeypatch.delenv("ARYX_OCR", raising=False)
    assert make_page_ocr(_Broker(_Spec("google"))) is None


def test_ocr_is_available_for_gemini_and_off_for_other_providers(monkeypatch):
    monkeypatch.setenv("ARYX_OCR", "auto")
    assert make_page_ocr(_Broker(_Spec("google"))) is not None
    assert make_page_ocr(_Broker(_Spec("openai"))) is not None
    assert make_page_ocr(_Broker(_Spec("ollama", key_ref=None))) is None
    assert make_page_ocr(_Broker(_Spec("anthropic"))) is None
    assert make_page_ocr(_Broker(_Spec("google"), key="")) is None       # no key


@pytest.mark.parametrize("value", ["", "off", "OFF", "0", "false", "no", "maybe"])
def test_anything_but_an_explicit_on_leaves_ocr_off(monkeypatch, value):
    monkeypatch.setenv("ARYX_OCR", value)
    assert make_page_ocr(_Broker(_Spec("google"))) is None


def test_the_page_budget_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("ARYX_OCR", "auto")
    monkeypatch.setenv("ARYX_OCR_MAX_PAGES", "7")
    assert make_page_ocr(_Broker(_Spec("google")))._max_pages == 7
    monkeypatch.setenv("ARYX_OCR_MAX_PAGES", "lots")
    assert make_page_ocr(_Broker(_Spec("google")))._max_pages == 30


def test_the_request_sent_to_the_model_carries_the_page_picture(monkeypatch):
    sent = {}

    def fake_post(url, body, headers, timeout=None):
        sent.update(url=url, body=body, headers=headers)
        return {"choices": [{"message": {"content": "| a | b |"}}]}

    import aryx.llm_providers as providers
    monkeypatch.setattr(providers, "post_json", fake_post)
    out = ocr_vision._transcribe_with("https://example.test/v1beta/openai/", "gemini-2.5-flash",
                                      "secret", b"\x89PNGdata")
    assert out == "| a | b |"
    assert sent["url"] == "https://example.test/v1beta/openai/chat/completions"
    assert sent["headers"] == {"Authorization": "Bearer secret"}
    parts = sent["body"]["messages"][0]["content"]
    assert parts[0]["type"] == "text" and parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert sent["body"]["temperature"] == 0


# ---- why a scan gave no text ---------------------------------------------------------

def test_a_scan_with_ocr_off_says_how_to_turn_it_on_and_where_the_images_go(tmp_path):
    from aryx.connectors import doc_router

    class _Chunks:
        def upsert_document(self, **_k): return 1

    msg = doc_router._no_text_message(tmp_path / "scan.pdf", None)
    assert "No readable text was found in scan.pdf" in msg
    assert "ARYX_OCR=auto" in msg and "sent to that provider" in msg


def test_a_model_that_cannot_read_images_is_named_in_the_message(tmp_path):
    from aryx.connectors import doc_router

    def refuses(_png):
        raise RuntimeError("HTTP 400: this model does not accept image input")

    ocr = PageOcr(refuses)
    list(PdfConnector(_blank_pdf(tmp_path), ocr=ocr).extract_pages())
    msg = doc_router._no_text_message(tmp_path / "scan.pdf", ocr)
    assert "OCR is on but the model could not read the page" in msg
    assert "does not accept image input" in msg
    assert "accepts images" in msg
