"""Demo support-data loader (G-demo): row inserts behind queries/*.sql.

Extracted from demo_ingest_api so the router stays slim and zero SQL lives
in Python (DB-Guard). All statements use SQLAlchemy named binds.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import text

from aryx.demo.support_data_generator import SupportDataGenerator
from aryx.queries import load

logger = logging.getLogger(__name__)

_COUNT_TABLES = ["support_customers", "support_sites", "support_devices",
                 "support_agents", "support_tickets", "support_resolutions",
                 "support_ticket_device_links"]


def _ids(session: Any, query: str) -> list[int]:
    """Fetch a single-column id list via a named query."""
    return [r[0] for r in session.execute(text(load(query))).fetchall()]


def _insert_all(session: Any, query: str, rows: list[dict]) -> None:
    """Run one insert statement per row, then commit the batch."""
    stmt = text(load(query))
    for row in rows:
        session.execute(stmt, row)
    session.commit()


def load_support_data(session: Any, ticket_count: int,
                      clean_first: bool) -> dict[str, int]:
    """Generate and land the synthetic support dataset.

    Args:
        session: Open SQLAlchemy session (caller owns commit/close).
        ticket_count: Number of tickets to generate (seeded, deterministic).
        clean_first: Truncate prior demo rows before loading.

    Returns:
        Row counts per demo table.
    """
    if clean_first:
        session.execute(text(load("cleanup_demo_data")))
        session.commit()

    gen = SupportDataGenerator(ticket_count=ticket_count, seed=42)
    _insert_all(session, "demo_insert_customer", gen.generate_customers())

    customer_ids = _ids(session, "demo_select_customer_ids")
    _insert_all(session, "demo_insert_site", gen.generate_sites(customer_ids))

    site_ids = _ids(session, "demo_select_site_ids")
    _insert_all(session, "demo_insert_device", gen.generate_devices(site_ids))

    _insert_all(session, "demo_insert_agent", gen.generate_agents())
    _insert_all(session, "demo_insert_expertise_tag", [
        {"tag_name": t["tag_name"], "description": t.get("description", "")}
        for t in gen.generate_expertise_tags()
    ])

    agent_ids = list(range(1, 16))
    tag_ids = list(range(1, 9))
    expertise = [
        {"agent_id": agent_id, "tag_id": tag_id}
        for agent_id in agent_ids
        for tag_id in random.sample(tag_ids,
                                    min(random.randint(1, 3), len(tag_ids)))
    ]
    _insert_all(session, "demo_insert_agent_expertise", expertise)

    tickets, links = gen.generate_tickets(site_ids, agent_ids)
    _insert_all(session, "demo_insert_ticket", tickets)

    device_ids = _ids(session, "demo_select_device_ids")
    link_rows = [
        {"ticket_id": link["ticket_index"] + 1,
         "device_id": device_ids[i % len(device_ids)],
         "device_role": link["device_role"]}
        for i, link in enumerate(links) if i < len(device_ids)
    ]
    _insert_all(session, "demo_insert_ticket_device_link", link_rows)

    _insert_all(session, "demo_insert_resolution",
                gen.generate_resolutions(ticket_count))

    counts = {}
    template = load("demo_count_rows")
    for table in _COUNT_TABLES:
        counts[table] = session.execute(
            text(template.format(table=table))).scalar()
    logger.info("demo data loaded tickets=%s", counts.get("support_tickets"))
    return counts
