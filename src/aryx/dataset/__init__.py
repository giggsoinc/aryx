"""Dataset Upload & Ingestion (C02).

Accepts a file, verifies its format and size, computes a SHA-256 content hash,
and stores an immutable, versioned raw snapshot. Any later cleaning happens on a
versioned working copy — the raw snapshot is never mutated.
"""

from aryx.dataset.ingest import register_dataset
from aryx.dataset.models import DatasetIngestResult

__all__ = ["register_dataset", "DatasetIngestResult"]
