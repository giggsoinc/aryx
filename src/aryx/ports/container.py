"""The adapter container — the one composition root call-sites depend on.

Call-sites ask the container for a port; the container resolves the configured
adapter class and constructs it with the right substrate coordinates. Swapping
adapters (Lite -> Oracle) happens here + in config, never at the call-site.

Phase 0 exposes the graph reader, already routed through real call-sites (ask,
graph, observability APIs). The graph is served straight from the relational
store, so there is no write-side graph port. The remaining ports are
added to this container as their migrations land (see the attack plan).
"""
from __future__ import annotations

from functools import lru_cache
from typing import cast

from aryx.config import get_settings
from aryx.edition import Edition, current_edition
from aryx.ports.config import adapter_config, resolve
from aryx.ports.protocols import GraphReaderPort


class Container:
    """Resolves capability ports for the active edition + adapter config.

    Adapter *classes* are cached (one import per port); instances are created
    per call because they bind to one workspace.
    """

    @lru_cache(maxsize=None)  # noqa: B019 - class-level cache of adapter types
    def _cls(self, port: str) -> type:
        """Import and cache the adapter class bound to ``port``."""
        return resolve(port)

    def graph_reader(self, workspace_id: int = 1) -> GraphReaderPort:
        """Return the read-side graph adapter for one workspace."""
        cls = self._cls("graph_reader")
        adapter = cls(get_settings().rdb_dsn, workspace_id)
        return cast(GraphReaderPort, adapter)

    def describe(self) -> dict[str, object]:
        """Edition + active adapter targets — for /admin diagnostics."""
        edition: Edition = current_edition()
        return {
            "edition": edition.value,
            "is_enterprise": edition.is_enterprise,
            "adapters": adapter_config().targets,
        }


@lru_cache(maxsize=1)
def ports() -> Container:
    """Return the process-wide container."""
    return Container()
