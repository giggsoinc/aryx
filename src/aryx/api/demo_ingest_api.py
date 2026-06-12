"""Demo ingest API — load + query synthetic support ticket data.

Row-insert loops live in aryx.demo.loader; every SQL statement lives in
queries/*.sql (DB-Guard). SQLAlchemy needs the explicit psycopg3 dialect
(``postgresql+psycopg://``) — plain ``postgresql://`` selects psycopg2.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from aryx.config import get_settings
from aryx.demo.loader import load_support_data
from aryx.queries import load

logger = logging.getLogger(__name__)


class LoadDemoRequest(BaseModel):
    """Demo load request: ticket volume + optional pre-clean."""

    ticket_count: int = Field(default=200, ge=50, le=500)
    clean_first: bool = True


class LoadDemoResponse(BaseModel):
    """Demo load result with per-table row counts."""

    status: str
    rows_created: dict[str, int]
    message: str
    timestamp: str


def _session() -> tuple[Any, Any]:
    """Open a SQLAlchemy session on the psycopg3 dialect; caller closes both."""
    dsn = get_settings().rdb_dsn.replace("postgresql://",
                                         "postgresql+psycopg://")
    engine = create_engine(dsn, echo=False)
    return engine, sessionmaker(bind=engine)()


def _rows(query: str, params: dict[str, Any],
          mapper) -> list[dict[str, Any]]:
    """Run one named select and map rows; 500 on failure."""
    engine, session = _session()
    try:
        rows = session.execute(text(load(query)), params).fetchall()
        return [mapper(r) for r in rows]
    except Exception as exc:  # noqa: BLE001 — surface as HTTP error
        raise HTTPException(500, f"Query failed: {exc}") from exc
    finally:
        session.close()
        engine.dispose()


def demo_ingest_router() -> APIRouter:
    """Build the /demo router."""
    router = APIRouter(prefix="/demo")

    @router.post("/load", response_model=LoadDemoResponse)
    def load_demo_data(req: LoadDemoRequest) -> dict[str, Any]:
        """Load synthetic support ticket data."""
        engine, session = _session()
        try:
            counts = load_support_data(session, req.ticket_count,
                                        req.clean_first)
            return {
                "status": "success",
                "rows_created": counts,
                "message": (f"Loaded {counts['support_tickets']} tickets, "
                            f"{counts['support_devices']} devices"),
                "timestamp": str(datetime.datetime.utcnow()),
            }
        except Exception as exc:  # noqa: BLE001 — rollback + audit the failure
            session.rollback()
            logger.exception("demo load failed: %s", exc)
            raise HTTPException(500, f"Load failed: {exc}") from exc
        finally:
            session.close()
            engine.dispose()

    @router.get("/tickets")
    def get_tickets(status: str | None = None,
                    priority: str | None = None) -> list[dict[str, Any]]:
        """Tickets, optionally filtered by status and/or priority."""
        return _rows("demo_select_tickets",
                     {"status": status, "priority": priority},
                     lambda r: {"id": r[0], "site_id": r[1], "status": r[2],
                                "priority": r[3], "symptom_text": r[4],
                                "assigned_agent_id": r[5],
                                "created_at": str(r[6]),
                                "resolved_at": str(r[7]) if r[7] else None})

    @router.get("/agents")
    def get_agents(level: str | None = None) -> list[dict[str, Any]]:
        """Agents, optionally filtered by level."""
        return _rows("demo_select_agents", {"level": level},
                     lambda r: {"id": r[0], "name": r[1], "level": r[2],
                                "specialty": r[3], "tickets_resolved": r[4]})

    @router.get("/resolutions/{ticket_id}")
    def get_resolutions(ticket_id: int) -> list[dict[str, Any]]:
        """Resolution chain for one ticket."""
        return _rows("demo_select_resolutions", {"ticket_id": ticket_id},
                     lambda r: {"id": r[0], "ticket_id": r[1],
                                "solution_type": r[2], "success_flag": r[3],
                                "created_at": str(r[4])})

    return router
