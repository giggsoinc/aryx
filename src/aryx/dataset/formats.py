"""Format detection + enumeration for C02 — CSV and JSON only, stdlib only.

`detect` verifies the MIME signature via magic bytes and rejects encrypted /
unsupported workbook containers before any parsing. `enumerate_data` returns the
columns and an estimated row count used to populate the dataset version record.
"""
from __future__ import annotations

import csv
import io
import json

from aryx.connectors.json_source import _flatten

SUPPORTED_EXTS = {".csv", ".json"}

# Compound File Binary (legacy .xls and encrypted OOXML containers).
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# ZIP local file header (.xlsx / .docx are zip containers).
_ZIP_MAGIC = b"PK\x03\x04"

# Cap rows scanned for JSON column discovery — a floor, not an exact schema.
_JSON_COLSCAN = 100


def detect(data: bytes, ext: str) -> tuple[str, str | None]:
    """Return (format, reject_reason). reject_reason None means accepted.

    Args:
        data: Raw uploaded bytes.
        ext: Lowercase file extension including the dot (e.g. '.csv').
    """
    head = data[:8]
    if head.startswith(_OLE_MAGIC):
        return "", "encrypted or unsupported workbook content (OLE/encrypted container)"
    if head[:4] == _ZIP_MAGIC:
        return "", "unsupported workbook content (.xlsx/zip); only csv and json are supported"
    if ext == ".json":
        try:
            # utf-8-sig strips a leading BOM (common in Excel/Windows exports).
            json.loads(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            return "json", "invalid json: not valid UTF-8"
        except json.JSONDecodeError as exc:
            return "json", f"invalid json: {exc}"
        except RecursionError:
            return "json", "invalid json: nesting too deep"
        return "json", None
    if ext == ".csv":
        if b"\x00" in head:
            return "", "unsupported binary content for a .csv file"
        return "csv", None
    return "", f"unsupported file type {ext!r}; only .csv and .json are supported"


def enumerate_data(data: bytes, fmt: str) -> tuple[list[str], int]:
    """Return (columns, row_count_estimate) for a supported format."""
    if fmt == "json":
        return _enumerate_json(data)
    return _enumerate_csv(data)


def _dedupe_headers(header: list[str]) -> list[str]:
    """Strip + de-collide duplicate column names (id, id -> id, id_2)."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for raw in header:
        name = raw.strip()
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 1
            out.append(name)
    return out


def _enumerate_csv(data: bytes) -> tuple[list[str], int]:
    # utf-8-sig strips a leading BOM so the first header isn't '﻿Id'.
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig", "ignore")))
    rows = list(reader)
    if not rows:
        return [], 0
    header = _dedupe_headers(rows[0])
    # Trailing blank lines shouldn't count as rows.
    body = [r for r in rows[1:] if any(cell.strip() for cell in r)]
    return header, len(body)


def _enumerate_json(data: bytes) -> tuple[list[str], int]:
    loaded = json.loads(data.decode("utf-8-sig"))
    rows = loaded if isinstance(loaded, list) else [loaded]
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows[:_JSON_COLSCAN]:
        if isinstance(row, dict):
            for key in _flatten(row):
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
    return columns, len(rows)
