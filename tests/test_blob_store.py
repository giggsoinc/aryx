"""Tests for the content-addressable dataset blob store — pure filesystem,
no DB, no network."""
from __future__ import annotations

import tempfile

import pytest

from aryx.store.blob_store import read_blob, write_blob

_HASH = "sha256:" + "a" * 64


def test_write_then_read_roundtrips() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ref = write_blob(tmp, _HASH, b"hello world")
        assert read_blob(tmp, ref) == b"hello world"


def test_write_creates_the_blob_dir_if_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        nested = f"{tmp}/does/not/exist/yet"
        ref = write_blob(nested, _HASH, b"data")
        assert read_blob(nested, ref) == b"data"


def test_ref_is_the_bare_hex_digest_not_the_sha256_prefix() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ref = write_blob(tmp, _HASH, b"data")
        assert ref == "a" * 64


def test_rewriting_the_same_hash_overwrites_cleanly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_blob(tmp, _HASH, b"first")
        ref = write_blob(tmp, _HASH, b"second")
        assert read_blob(tmp, ref) == b"second"


def test_malformed_hash_is_rejected_not_used_as_a_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError):
            write_blob(tmp, "sha256:not-actually-hex!!", b"data")


def test_path_traversal_attempt_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError):
            write_blob(tmp, "sha256:../../../../etc/passwd", b"data")


def test_read_of_unknown_ref_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            read_blob(tmp, "b" * 64)
