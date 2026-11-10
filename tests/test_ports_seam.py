"""Phase 0 seam tests — prove a substrate swap is a config flip, not surgery.

The whole anti-surgery thesis for Aryx-o (v2.1 on Oracle) rests on one claim:
an operator replaces the class backing a capability port via one env var, and
every call-site keeps working unchanged. These tests pin that contract.

Deliberately substrate-free: they assert on which class the container resolves
and how it constructs it — no live Postgres. That is the point of the seam: wiring is verifiable without the stack.
"""
from __future__ import annotations

import pytest

from aryx.config import get_settings
from aryx.edition import Edition, current_edition
from aryx.ports.config import _target_for, resolve
from aryx.ports.container import Container


def test_lite_defaults_point_at_shipped_classes() -> None:
    """With no overrides, the graph port targets the Postgres reader (by name,
    so the assertion never opens a connection). The graph is served straight
    from the relational store, so there is no write-side graph port."""
    assert _target_for("graph_reader") == "aryx.graph.pg_reader:PostgresGraphReader"
    assert _target_for("graph_store") == ""


def test_env_override_swaps_adapter_without_touching_callsites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE anti-surgery proof: flip one env var → a different class backs the
    port and the container constructs it, with zero changes to ask_api /
    graph_api."""
    monkeypatch.setenv(
        "ARYX_ADAPTER_GRAPH_READER",
        "test_ports_seam:_StubGraphReader",
    )
    assert resolve("graph_reader") is _StubGraphReader

    reader = Container().graph_reader(workspace_id=7)
    assert isinstance(reader, _StubGraphReader)
    # Constructed with the right substrate coordinates, wired by the container:
    assert reader.dsn == get_settings().rdb_dsn  # from Settings.rdb_dsn
    assert reader.workspace_id == 7
    # And it still answers the port contract the call-sites rely on:
    assert reader.find_entities() == []


def test_there_is_no_graph_write_port() -> None:
    """The graph is a read of the relational store; nothing writes to it."""
    assert not hasattr(Container(), "graph_store")


def test_bad_adapter_target_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured swap raises immediately — never silently no-ops."""
    monkeypatch.setenv("ARYX_ADAPTER_GRAPH_READER", "no.such.module:Nope")
    with pytest.raises(ImportError):
        resolve("graph_reader")


def test_edition_defaults_to_lite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset / unknown ARYX_EDITION resolves to Lite; aryx-o unlocks v2."""
    current_edition.cache_clear()
    monkeypatch.delenv("ARYX_EDITION", raising=False)
    assert current_edition() is Edition.LITE
    assert not current_edition().is_enterprise

    current_edition.cache_clear()
    monkeypatch.setenv("ARYX_EDITION", "aryx-o")
    assert current_edition() is Edition.ARYX_O
    assert current_edition().is_enterprise
    current_edition.cache_clear()


class _StubGraphReader:
    """A fake substrate adapter — proves the swap binds any matching class."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        self.dsn = dsn
        self.workspace_id = workspace_id

    def find_entities(self, ontology_type=None, name=None, limit=50):  # noqa: ANN001, ANN201, D102
        return []
