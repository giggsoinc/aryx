"""Slice 2 — Fernet secret store + datasource quiz contract."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _set_test_key(monkeypatch):
    """Pin ARYX_SECRET_KEY for deterministic test runs."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv("ARYX_SECRET_KEY", Fernet.generate_key().decode())


def test_roundtrip_recovers_plaintext():
    from aryx import datasource_secrets as ds
    ct = ds.encrypt("hunter2")
    assert ct and ct != "hunter2"
    assert ds.decrypt(ct) == "hunter2"


def test_mask_is_stable_and_non_reversible():
    from aryx import datasource_secrets as ds
    m1 = ds.mask("hunter2")
    m2 = ds.mask("hunter2")
    assert m1 == m2 and m1.startswith("••••") and "hunter2" not in m1


def test_decrypt_rejects_wrong_key(monkeypatch):
    from cryptography.fernet import Fernet
    from aryx import datasource_secrets as ds
    ct = ds.encrypt("hunter2")
    monkeypatch.setenv("ARYX_SECRET_KEY", Fernet.generate_key().decode())
    with pytest.raises(ValueError):
        ds.decrypt(ct)


def test_empty_passes_through():
    from aryx import datasource_secrets as ds
    assert ds.encrypt("") == "" and ds.decrypt("") == "" and ds.mask("") == ""


def test_quiz_known_kinds():
    from aryx.datasource_quiz import quiz_for, supported_kinds
    kinds = supported_kinds()
    assert {"postgresql", "mysql", "oracle", "docs", "rest"} <= set(kinds)
    pg = quiz_for("postgresql")
    assert pg["kind"] == "postgresql"
    password = [f for f in pg["fields"] if f["name"] == "password"][0]
    assert password["secret"] is True
    assert quiz_for("zorp").get("error")


def test_datasource_tool_specs_cover_five():
    from aryx.mcp.tools_datasource import datasource_tool_specs
    names = {t.name for t in datasource_tool_specs()}
    assert names == {
        "datasource_quiz", "datasource_add", "datasource_list",
        "datasource_test", "datasource_delete",
    }
