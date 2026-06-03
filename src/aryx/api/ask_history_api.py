"""Ask history API — list persisted Q/A turns for a workspace."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from aryx.config import get_settings
from aryx.store.ask_history_store import AskHistoryStore

logger = logging.getLogger(__name__)


def ask_history_router() -> APIRouter:
    """Build the /ask/history router."""
    router = APIRouter(prefix="/ask/history")

    @router.get("")
    def list_history(workspace_id: int = 1,
                     limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent N Q/A turns for a workspace."""
        store = AskHistoryStore(get_settings().rdb_dsn)
        try:
            return store.recent(workspace_id, limit)
        finally:
            store.close()

    return router
