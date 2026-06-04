"""Demo ingest API — load synthetic support ticket data."""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from aryx.config import get_settings
from aryx.demo.support_data_generator import SupportDataGenerator

logger = logging.getLogger(__name__)


class LoadDemoRequest(BaseModel):
    ticket_count: int = Field(default=200, ge=50, le=500)
    clean_first: bool = True


class LoadDemoResponse(BaseModel):
    status: str
    rows_created: dict[str, int]
    message: str
    timestamp: str


class TicketResponse(BaseModel):
    id: int
    site_id: int
    status: str
    priority: str
    symptom_text: str
    assigned_agent_id: int | None
    created_at: str
    resolved_at: str | None


class AgentResponse(BaseModel):
    id: int
    name: str
    level: str
    specialty: str
    tickets_resolved: int


class ResolutionResponse(BaseModel):
    id: int
    ticket_id: int
    solution_type: str
    success_flag: bool
    created_at: str


def demo_ingest_router() -> APIRouter:
    """Build /api/demo router."""
    router = APIRouter(prefix="/demo")
    settings = get_settings()

    @router.post("/load", response_model=LoadDemoResponse)
    def load_demo_data(req: LoadDemoRequest) -> dict[str, Any]:
        """Load synthetic support ticket data."""
        engine = create_engine(settings.rdb_dsn, echo=False)
        session = sessionmaker(bind=engine)()

        try:
            if req.clean_first:
                cleanup = Path(__file__).parent.parent / "queries" / "cleanup_demo_data.sql"
                session.execute(text(cleanup.read_text()))
                session.commit()

            gen = SupportDataGenerator(ticket_count=req.ticket_count, seed=42)
            customers = gen.generate_customers()
            for cust in customers:
                session.execute(
                    text("INSERT INTO support_customers (name, sla_tier, primary_contact, created_at) VALUES (:name, :sla_tier, :primary_contact, :created_at)"),
                    cust,
                )
            session.commit()

            customer_ids = [r[0] for r in session.execute(text("SELECT id FROM support_customers ORDER BY id")).fetchall()]
            sites = gen.generate_sites(customer_ids)
            for site in sites:
                session.execute(
                    text("INSERT INTO support_sites (customer_id, location, site_type, device_count, created_at) VALUES (:customer_id, :location, :site_type, :device_count, :created_at)"),
                    site,
                )
            session.commit()

            site_ids = [r[0] for r in session.execute(text("SELECT id FROM support_sites ORDER BY id")).fetchall()]
            devices = gen.generate_devices(site_ids)
            for device in devices:
                session.execute(
                    text("INSERT INTO support_devices (site_id, model, firmware_version, config_hash, install_date, status, last_heartbeat, created_at) VALUES (:site_id, :model, :firmware_version, :config_hash, :install_date, :status, :last_heartbeat, :created_at)"),
                    device,
                )
            session.commit()

            agents = gen.generate_agents()
            for agent in agents:
                session.execute(
                    text("INSERT INTO support_agents (name, level, specialty, max_concurrent_tickets, tickets_resolved, created_at) VALUES (:name, :level, :specialty, :max_concurrent_tickets, :tickets_resolved, :created_at)"),
                    agent,
                )
            session.commit()

            tags = gen.generate_expertise_tags()
            for tag in tags:
                session.execute(
                    text("INSERT INTO support_expertise_tags (tag_name, description, created_at) VALUES (:tag_name, :description, CURRENT_TIMESTAMP)"),
                    {"tag_name": tag["tag_name"], "description": tag.get("description", "")},
                )
            session.commit()

            agent_ids = list(range(1, 16))
            tag_ids = list(range(1, 9))
            for agent_id in agent_ids:
                for tag_id in random.sample(tag_ids, min(random.randint(1, 3), len(tag_ids))):
                    session.execute(
                        text("INSERT INTO support_agent_expertise (agent_id, tag_id) VALUES (:agent_id, :tag_id)"),
                        {"agent_id": agent_id, "tag_id": tag_id},
                    )
            session.commit()

            tickets, links = gen.generate_tickets(site_ids, agent_ids)
            for ticket in tickets:
                session.execute(
                    text("INSERT INTO support_tickets (site_id, created_by, assigned_agent_id, status, priority, symptom_text, resolution_notes, resolved_at, escalation_reason, created_at, updated_at) VALUES (:site_id, :created_by, :assigned_agent_id, :status, :priority, :symptom_text, :resolution_notes, :resolved_at, :escalation_reason, :created_at, :updated_at)"),
                    ticket,
                )
            session.commit()

            device_ids = [r[0] for r in session.execute(text("SELECT id FROM support_devices ORDER BY id")).fetchall()]
            for i, link in enumerate(links):
                if i < len(device_ids):
                    session.execute(
                        text("INSERT INTO support_ticket_device_links (ticket_id, device_id, device_role) VALUES (:ticket_id, :device_id, :device_role)"),
                        {"ticket_id": link["ticket_index"] + 1, "device_id": device_ids[i % len(device_ids)], "device_role": link["device_role"]},
                    )
            session.commit()

            resolutions = gen.generate_resolutions(req.ticket_count)
            for resolution in resolutions:
                session.execute(
                    text("INSERT INTO support_resolutions (ticket_id, solution_type, applied_by_agent_id, knowledge_link, success_flag, created_at, updated_at) VALUES (:ticket_id, :solution_type, :applied_by_agent_id, :knowledge_link, :success_flag, :created_at, CURRENT_TIMESTAMP)"),
                    resolution,
                )
            session.commit()

            counts = {k: session.execute(text(f"SELECT COUNT(*) FROM {k}")).scalar()
                     for k in ["support_customers", "support_sites", "support_devices", "support_agents", "support_tickets", "support_resolutions", "support_ticket_device_links"]}

            return {
                "status": "success",
                "rows_created": counts,
                "message": f"Loaded {counts['support_tickets']} tickets, {counts['support_devices']} devices",
                "timestamp": str(__import__("datetime").datetime.utcnow()),
            }

        except Exception as exc:
            session.rollback()
            logger.exception(f"Load failed: {exc}")
            raise HTTPException(500, f"Load failed: {exc}") from exc
        finally:
            session.close()
            engine.dispose()

    @router.get("/tickets", response_model=list[TicketResponse])
    def get_tickets(status: str | None = None, priority: str | None = None) -> list[dict[str, Any]]:
        """Get tickets, optionally filtered."""
        engine = create_engine(settings.rdb_dsn, echo=False)
        session = sessionmaker(bind=engine)()

        try:
            query = "SELECT id, site_id, status, priority, symptom_text, assigned_agent_id, created_at, resolved_at FROM support_tickets WHERE 1=1"
            params = {}
            if status:
                query += " AND status = :status"
                params["status"] = status
            if priority:
                query += " AND priority = :priority"
                params["priority"] = priority
            query += " ORDER BY created_at DESC LIMIT 100"

            rows = session.execute(text(query), params).fetchall()
            return [{"id": r[0], "site_id": r[1], "status": r[2], "priority": r[3], "symptom_text": r[4], "assigned_agent_id": r[5], "created_at": str(r[6]), "resolved_at": str(r[7]) if r[7] else None} for r in rows]
        except Exception as exc:
            raise HTTPException(500, f"Query failed: {exc}") from exc
        finally:
            session.close()
            engine.dispose()

    @router.get("/agents", response_model=list[AgentResponse])
    def get_agents(level: str | None = None) -> list[dict[str, Any]]:
        """Get agents, optionally filtered by level."""
        engine = create_engine(settings.rdb_dsn, echo=False)
        session = sessionmaker(bind=engine)()

        try:
            query = "SELECT id, name, level, specialty, tickets_resolved FROM support_agents WHERE 1=1"
            params = {}
            if level:
                query += " AND level = :level"
                params["level"] = level
            query += " ORDER BY level DESC, tickets_resolved DESC"

            rows = session.execute(text(query), params).fetchall()
            return [{"id": r[0], "name": r[1], "level": r[2], "specialty": r[3], "tickets_resolved": r[4]} for r in rows]
        except Exception as exc:
            raise HTTPException(500, f"Query failed: {exc}") from exc
        finally:
            session.close()
            engine.dispose()

    @router.get("/resolutions/{ticket_id}", response_model=list[ResolutionResponse])
    def get_resolutions(ticket_id: int) -> list[dict[str, Any]]:
        """Get resolution chain for a ticket."""
        engine = create_engine(settings.rdb_dsn, echo=False)
        session = sessionmaker(bind=engine)()

        try:
            rows = session.execute(
                text("SELECT id, ticket_id, solution_type, success_flag, created_at FROM support_resolutions WHERE ticket_id = :ticket_id ORDER BY created_at"),
                {"ticket_id": ticket_id},
            ).fetchall()
            return [{"id": r[0], "ticket_id": r[1], "solution_type": r[2], "success_flag": r[3], "created_at": str(r[4])} for r in rows]
        except Exception as exc:
            raise HTTPException(500, f"Query failed: {exc}") from exc
        finally:
            session.close()
            engine.dispose()

    return router
