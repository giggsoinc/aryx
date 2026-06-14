"""Adapter selection config — which concrete class backs each port.

Every port maps to an import target ``module:Class``. The Lite defaults wrap
today's commodity stack. An operator (or the Aryx-o build) overrides any single
port via an env var without touching call-sites::

    ARYX_ADAPTER_GRAPH_READER=aryx.adapters.oracle.graph:OracleGraphReader

That one line is the whole "swap the substrate" story — no spinal surgery.
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

# Lite defaults: today's shipped implementations already satisfy the ports.
_DEFAULTS: dict[str, str] = {
    "graph_reader": "aryx.graph.reader:GraphReader",
    "graph_store": "aryx.graph.falkor_store:FalkorStore",
}

_ENV_PREFIX = "ARYX_ADAPTER_"


def _target_for(port: str) -> str:
    """Return the ``module:Class`` target for a port, env override winning."""
    env_key = f"{_ENV_PREFIX}{port.upper()}"
    return os.getenv(env_key, _DEFAULTS.get(port, ""))


def resolve(port: str) -> type[Any]:
    """Import and return the adapter class bound to ``port``.

    Raises:
        KeyError: the port has no default and no override.
        ImportError / AttributeError: the configured target is unloadable —
            surfaced loudly so a bad swap fails fast, never silently.
    """
    target = _target_for(port)
    if not target:
        raise KeyError(f"no adapter configured for port {port!r}")
    module_name, _, class_name = target.partition(":")
    if not class_name:
        raise ValueError(f"adapter target {target!r} must be 'module:Class'")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


@dataclass(frozen=True)
class AdapterConfig:
    """Snapshot of which class backs each port (for diagnostics / the API)."""

    targets: dict[str, str]

    @classmethod
    def current(cls) -> "AdapterConfig":
        """Capture the live target for every known port."""
        ports = set(_DEFAULTS) | {
            k[len(_ENV_PREFIX):].lower()
            for k in os.environ
            if k.startswith(_ENV_PREFIX)
        }
        return cls(targets={p: _target_for(p) for p in sorted(ports)})


@lru_cache(maxsize=1)
def adapter_config() -> AdapterConfig:
    """Process-wide cached adapter snapshot."""
    return AdapterConfig.current()
