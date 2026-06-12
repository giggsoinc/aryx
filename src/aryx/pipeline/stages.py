"""Stage-checkpoint guard for pipeline runs (G5).

Wraps each pipeline stage in a durable status row: 'running' at entry,
'done' on success, 'failed' on exception. On resume, stages already 'done'
are skipped; a leftover 'running' means the process died — redo the stage.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from aryx.store.checkpoint_store import StageTracker

logger = logging.getLogger(__name__)


class StageRunner:
    """Per-run stage execution guard with skip-on-resume semantics."""

    def __init__(self, dsn: str, run_id: int, resume: bool) -> None:
        """Load prior stage statuses when resuming."""
        self._tracker = StageTracker(dsn)
        self._run_id = run_id
        self._done: set[str] = set()
        if resume:
            statuses = self._tracker.statuses(run_id)
            self._done = {s for s, st in statuses.items() if st == "done"}
            logger.info("resume run=%s skipping stages=%s",
                        run_id, sorted(self._done))

    def skip(self, stage: str) -> bool:
        """True when a resumed run already completed this stage."""
        return stage in self._done

    @contextmanager
    def stage(self, name: str,
              detail: dict[str, Any] | None = None) -> Iterator[None]:
        """Run one stage under checkpoint accounting."""
        self._tracker.start(self._run_id, name)
        try:
            yield
        except Exception as exc:
            self._tracker.fail(self._run_id, name, str(exc))
            raise
        self._tracker.finish(self._run_id, name, detail)
