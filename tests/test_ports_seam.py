"""Phase 0 seam tests — prove a substrate swap is a config flip, not surgery.

The whole anti-surgery thesis for Aryx-o (v2.1 on Oracle) rests on one claim:
an operator replaces the class backing a capability port via one env var, and
every call-site keeps working unchanged. These tests pin that contract.

Deliberately substrate-free: they assert on which class the container resolves
and how it constructs it — no live Postgres / FalkorDB, not even the falkordb
driver. That is the point of the seam: wiring is verifiable without the stack.
"""
from __future__ import annotations

import pytest

from aryx.edition import Edition, current_edition
from aryx.ports.config import _target_for, resolve
from aryx.ports.container import Container


def test_lite_defaults_point_at_shipped_classes() -> None:
    """With no overrides, each port targets today's commodity stack (by name,
    so the assertion never imports the falkordb driver)."""
    assert _target_for("graph_reader") == "aryx.graph.reader:GraphReader"
    assert _target_for("graph_store") == "aryx.graph.falkor_store:FalkorStore"


def test_env_override_swaps_adapter_without_touching_callsites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE anti-surgery proof: flip one env var → a different class backs the
    port and the container constructs it, with zero changes to ask_api /
    graph_api / observability_api."""
    monkeypatch.setenv(
        "ARYX_ADAPTER_GRAPH_READER",
        "test_ports_seam:_StubGraphReader",
    )
    assert resolve("graph_reader") is _StubGraphReader

    reader = Container().graph_reader(workspace_id=7)
    assert isinstance(reader, _StubGraphReader)
    # Constructed with the right substrate coordinates, wired by the container:
    assert reader.url  # from Settings.graph_url
    assert reader.graph == "aryx_ws_7"  # from ws_graph(workspace_id)
    # And it still answers the port contract the call-sites rely on:
    assert reader.find_entities() == []


def test_graph_store_port_swaps_the_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write side is on the same seam — proving the vertical, not one method."""
    monkeypatch.setenv(
        "ARYX_ADAPTER_GRAPH_STORE",
        "test_ports_seam:_StubGraphStore",
    )
    store = Container().graph_store(workspace_id=3)
    assert isinstance(store, _StubGraphStore)
    assert store.graph == "aryx_ws_3"


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

    def __init__(self, url: str, graph: str = "aryx") -> None:
        self.url = url
        self.graph = graph

    def find_entities(self, ontology_type=None, name=None, limit=50):  # noqa: ANN001, ANN201, D102
        return []


class _StubGraphStore:
    """A fake write-side adapter for the swap proof."""

    def __init__(self, url: str, graph: str = "aryx") -> None:
        self.url = url
        self.graph = graph
