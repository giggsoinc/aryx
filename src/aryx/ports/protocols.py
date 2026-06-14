"""The six capability-port contracts (typing.Protocol).

These are *structural* interfaces: today's concrete classes (FalkorStore,
GraphReader, the broker LLM dispatch, the Postgres stores) already satisfy them
by duck typing, so the default Lite adapters need no wrapper. A future Oracle /
Fabric / Vertex adapter just has to match the same shape to be swapped in via
config — the call-sites never change.

Phase 0 wires GraphReaderPort / GraphStorePort end-to-end. The other four are
defined here as the forward contract and are migrated incrementally (see the
attack plan); their signatures mirror what callers use today so the migration
is mechanical, not a redesign.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphReaderPort(Protocol):
    """Read side of the knowledge-graph projection."""

    def get_entity(self, entity_id: int) -> dict[str, Any] | None: ...
    def find_entities(self, ontology_type: str | None = None,
                      name: str | None = None, limit: int = 50) -> list[dict[str, Any]]: ...
    def neighbors(self, entity_id: int) -> list[dict[str, Any]]: ...
    def all_relationships(self) -> list[dict[str, Any]]: ...
    def provenance(self, entity_id: int) -> list[dict[str, Any]]: ...
    def shortest_path(self, src: int, dst: int, max_hops: int = 6) -> list[dict[str, Any]]: ...


@runtime_checkable
class GraphStorePort(Protocol):
    """Write side of the knowledge-graph projection."""

    def clear(self) -> None: ...
    def add_entity(self, entity_id: int, ontology_type: str,
                   attributes: dict[str, Any], labels: list[str] | None = None,
                   iri: str | None = None) -> None: ...
    def add_provenance(self, entity_id: int, system: str, dataset: str,
                       record_id: str) -> None: ...
    def remove_entity(self, entity_id: int) -> None: ...
    def add_relationship(self, source_id: int, target_id: int, name: str) -> None: ...


@runtime_checkable
class RelationalPort(Protocol):
    """Canonical relational store (source of truth). Forward contract."""

    def close(self) -> None: ...


@runtime_checkable
class VectorPort(Protocol):
    """Embedding storage + similarity search. Forward contract."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class LlmPort(Protocol):
    """Multi-provider LLM dispatch. Forward contract."""

    def complete_json(self, system: str, user: str,
                      schema: dict[str, Any]) -> dict[str, Any]: ...
    def complete_text(self, system: str, user: str) -> tuple[str, int, int]: ...


@runtime_checkable
class ReasonerPort(Protocol):
    """Axiom validation / rule evaluation. Forward contract."""

    def validate_workspace(self, workspace_id: int) -> dict[str, Any]: ...


@runtime_checkable
class ComputePort(Protocol):
    """Background / parallel work dispatch. Forward contract."""

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...
