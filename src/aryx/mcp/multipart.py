"""Hand-rolled multipart/form-data encoding for the MCP ingest shim.

Stdlib only — no extra HTTP client dependency. Split from ingest_hitl.py
for the file-length cap, and because the two validators below encode a
security distinction worth reading on its own.
"""
from __future__ import annotations

import mimetypes
import uuid


def _body_safe(value: str, what: str) -> str:
    """Reject a BODY-bound value carrying CR/LF.

    The raw multipart body is hand-built below with plain f-strings, so an
    unescaped '\\r'/'\\n' would let the caller close the current part and
    inject a fake boundary — smuggling additional form fields (e.g. a
    second workspace_id) past the real ones. CR/LF is the whole attack
    surface for a value that lands AFTER the blank line: those bytes are
    never parsed as a header, so a quote among them is inert.

    Quotes are therefore allowed here. Rejecting them made every JSON
    field unusable — `fk_links` and `graph_plan` are JSON-serialised, and
    any non-empty structure contains '"', so only an empty list ever got
    through. See _header_safe for values that DO land in a header line.
    """
    if any(c in value for c in ("\r", "\n")):
        raise ValueError(f"{what} contains a control character: {value!r}")
    return value


def _header_safe(value: str, what: str) -> str:
    """Reject a HEADER-bound value carrying CR/LF or a quote.

    Stricter than _body_safe because this value is interpolated INSIDE a
    header line, between double quotes — `filename="{value}"`. A quote
    would close that string early and let the remainder be read as further
    header parameters. There are no escaping rules to lean on in this
    format, so refusing outright is the safe move.
    """
    if any(c in value for c in ("\r", "\n", '"')):
        raise ValueError(f"{what} contains a control character or quote: {value!r}")
    return value


def encode_multipart(fields: dict[str, str],
                      files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body by hand (stdlib only — no extra
    HTTP client dependency). Returns (body, boundary)."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        value = _body_safe(value, f"field {key!r}")
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
            f"\r\n\r\n{value}\r\n".encode())
    for field_name, filename, data in files:
        filename = _header_safe(filename, "filename")
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary
