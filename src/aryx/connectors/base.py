"""Connector interface for source extraction (pipeline stage 1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from aryx.models import RawRecord


class Connector(ABC):
    """Abstract source connector yielding raw records in batches."""

    @abstractmethod
    def extract(self) -> Iterator[RawRecord]:
        """Yield raw records from the source system."""
        raise NotImplementedError

    def close(self) -> None:
        """Release any held resources. Override when needed."""
