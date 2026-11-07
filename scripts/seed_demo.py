"""Seed demo data: five companies and four relationships, in Postgres.

The graph is read live from Postgres, so seeding the tables is seeding the
graph. Safe to re-run: companies that already exist (by name) are reused and
existing relationships are not duplicated.

Run on the server after deploy:
  python scripts/seed_demo.py [--workspace-id N]
"""
from __future__ import annotations

import argparse
import logging

from aryx.config import get_settings
from aryx.models import Relationship, ResolvedEntity
from aryx.store.entity_store import EntityStore
from aryx.store.migrate import apply_migrations

logger = logging.getLogger("seed_demo")

COMPANIES = ["Acme Corp", "Globex LLC", "Initech", "Umbrella Co", "Stark Industries"]

# (source company, target company, relationship name)
RELATIONSHIPS = [
    ("Globex LLC", "Acme Corp", "SUPPLIES"),
    ("Stark Industries", "Initech", "ACQUIRED"),
    ("Umbrella Co", "Globex LLC", "PARTNERS_WITH"),
    ("Acme Corp", "Umbrella Co", "COMPETES_WITH"),
]


def seed(dsn: str, workspace_id: int) -> None:
    """Create the demo companies and relationships that do not exist yet."""
    estore = EntityStore(dsn, workspace_id)
    by_name = {attrs.get("name"): eid for eid, otype, attrs in estore.list_entities()
               if otype == "Company"}
    missing = [n for n in COMPANIES if n not in by_name]
    logger.info("creating %d companies (%d already exist)", len(missing),
                len(COMPANIES) - len(missing))
    estore.save([(ResolvedEntity(ontology_type="Company", attributes={"name": n},
                                 confidence=1.0), []) for n in missing])
    by_name = {attrs.get("name"): eid for eid, otype, attrs in estore.list_entities()
               if otype == "Company"}
    existing = set(estore.list_relationships())
    fresh = [Relationship(source_entity_id=by_name[s], target_entity_id=by_name[t],
                          name=rel, confidence=1.0)
             for s, t, rel in RELATIONSHIPS
             if (by_name[s], by_name[t], rel) not in existing]
    estore.save_relationships(fresh)
    logger.info("added %d relationships (%d already existed)", len(fresh),
                len(RELATIONSHIPS) - len(fresh))
    for s, t, rel in RELATIONSHIPS:
        logger.info("  %s --[%s]--> %s", s, rel, t)


def main() -> None:
    """Parse arguments and seed the chosen workspace."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace-id", type=int, default=1)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dsn = get_settings().rdb_dsn
    apply_migrations(dsn)
    seed(dsn, args.workspace_id)
    logger.info("Done.")


if __name__ == "__main__":
    main()
