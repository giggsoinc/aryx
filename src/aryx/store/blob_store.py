"""Content-addressable on-disk storage for raw dataset upload bytes (C02).

Keyed by content_hash (already computed by aryx.dataset.ingest as
"sha256:<hexdigest>") rather than any user-supplied dataset_id/filename —
that hash is a fixed-format hex string, never resolvable to a path-traversal
attempt, and it already gives the "same content stored once" guarantee the
dataset_version table promises. Bytes never touch Postgres (see migration
0043 and DatasetStore).
"""
from __future__ import annotations

import re
from pathlib import Path

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _safe_key(content_hash: str) -> str:
    """Strip the "sha256:" prefix and validate the remainder is pure hex.

    Raises ValueError rather than silently accepting anything that isn't
    the exact shape aryx.dataset.ingest produces — a blob key is the one
    place a malformed value would otherwise become a filesystem path.
    """
    digest = content_hash.removeprefix("sha256:")
    if not _HASH_RE.match(digest):
        raise ValueError(f"content_hash is not a sha256 hex digest: {content_hash!r}")
    return digest


def write_blob(blob_dir: str, content_hash: str, data: bytes) -> str:
    """Write `data` under its content hash; returns the stored ref.

    Idempotent — re-writing the same hash overwrites with identical bytes
    (same content, by definition), never partially.
    """
    key = _safe_key(content_hash)
    root = Path(blob_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / key
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)  # atomic on the same filesystem
    return key


def read_blob(blob_dir: str, ref: str) -> bytes:
    """Read back bytes written under `ref` (a value returned by write_blob)."""
    key = _safe_key(ref)
    return (Path(blob_dir) / key).read_bytes()
