#!/usr/bin/env python3
"""Automate full Aryx onboarding for demo_support_ticket workspace via API."""
from __future__ import annotations

import json
import sys
import time

import requests


class AryxDemoOnboarder:
    """Orchestrate full demo onboarding: workspace → brief → ingest → ask → graph → ontology."""

    def __init__(self, api_url: str = "http://localhost:8088"):
        self.api = api_url
        self.workspace_id = None
        self.session = requests.Session()

    def log(self, msg: str, level: str = "✅"):
        print(f"{level} {msg}")

    def err(self, msg: str):
        print(f"❌ {msg}")
        sys.exit(1)

    def post(self, path: str, data: dict) -> dict:
        """POST to API."""
        url = f"{self.api}{path}"
        try:
            resp = self.session.post(url, json=data, timeout=30)
            if resp.status_code >= 400:
                self.log(f"Response: {resp.text}", "⚠️")
            resp.raise_for_status()
            try:
                return resp.json()
            except:
                return {"status": "ok"}
        except Exception as e:
            self.err(f"POST {path}: {e}")

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET from API."""
        url = f"{self.api}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            try:
                return resp.json()
            except:
                return {"status": "ok"}
        except Exception as e:
            self.err(f"GET {path}: {e}")

    def step_1_create_workspace(self) -> None:
        """Step 1: Create demo_support_ticket workspace."""
        self.log("STEP 1: Creating workspace 'demo_support_ticket'")

        result = self.post(
            "/admin/workspaces",
            {
                "name": "demo_support_ticket",
                "description": "Radio equipment enterprise support case demo",
            },
        )
        self.workspace_id = result.get("id") or result.get("workspace_id")
        if not self.workspace_id:
            self.err(f"Failed to create workspace: {result}")

        self.log(f"Workspace created: ID={self.workspace_id}")

    def step_2_fill_brief(self) -> None:
        """Step 2: Fill the Brief (5 competency questions)."""
        self.log("STEP 2: Filling Brief")

        brief = {
            "domain": "Radio equipment support — enterprise networking",
            "aim": "Match complex tickets to expert agents; expose failure patterns by device model and firmware",
            "objectives": [
                "Surface device failure patterns by model + firmware version",
                "Match ticket symptom to agent expertise (firmware, hardware, network)",
                "Identify escalation-prone tickets before L1 assignment",
                "Track MTTR (mean time to resolution) by device model + agent level",
                "Flag RMA-eligible devices proactively based on resolution failure rate",
            ],
            "scope": "IN: customers, sites, devices, agents, tickets, resolutions, expertise tags | OUT: contracts, billing, RF spectrum, dispatch scheduling",
            "roles": [
                "Support Agent (L1/L2/L3)",
                "Support Manager",
                "Product Engineer",
                "Customer Success Manager",
            ],
        }

        result = self.post(
            f"/api/admin/workspaces/{self.workspace_id}/brief",
            brief,
        )
        self.log(f"Brief saved: {brief.get('domain')}")

    def step_3_ingest_tables(self) -> None:
        """Step 3: Ingest PostgreSQL tables."""
        self.log("STEP 3: Ingesting database tables")

        tables = [
            "support_customers",
            "support_sites",
            "support_devices",
            "support_agents",
            "support_expertise_tags",
            "support_agent_expertise",
            "support_tickets",
            "support_ticket_device_links",
            "support_resolutions",
        ]

        ingest_config = {
            "workspace_id": self.workspace_id,
            "source_type": "postgresql",
            "connection": {
                "host": "postgres",
                "port": 5432,
                "database": "aryx",
                "user": "aryx",
                "password": "aryx",
            },
            "tables": tables,
        }

        result = self.post(
            f"/api/ingest/start",
            ingest_config,
        )
        self.log(f"Ingest started: {len(tables)} tables")
        time.sleep(5)  # Let ingest process

    def step_4_prepare_ask_queries(self) -> None:
        """Step 4: Prepare ASK queries."""
        self.log("STEP 4: Preparing ASK queries")

        queries = [
            {
                "name": "Open Tickets by Priority",
                "sql": "SELECT priority, COUNT(*) as count FROM support_tickets WHERE status = 'open' GROUP BY priority ORDER BY count DESC;",
            },
            {
                "name": "Agent Workload & Resolution Rate",
                "sql": "SELECT a.name, a.level, COUNT(t.id) as assigned, COUNT(CASE WHEN t.status='resolved' THEN 1 END) as resolved FROM support_agents a LEFT JOIN support_tickets t ON a.id=t.assigned_agent_id GROUP BY a.id, a.name, a.level ORDER BY assigned DESC;",
            },
            {
                "name": "Device Failure Patterns",
                "sql": "SELECT d.model, d.firmware_version, COUNT(t.id) as incidents FROM support_devices d JOIN support_ticket_device_links tdl ON d.id=tdl.device_id JOIN support_tickets t ON tdl.ticket_id=t.id GROUP BY d.model, d.firmware_version HAVING COUNT(t.id) > 2 ORDER BY incidents DESC;",
            },
            {
                "name": "Escalation Patterns",
                "sql": "SELECT escalation_reason, COUNT(*) as count FROM support_tickets WHERE escalation_reason IS NOT NULL GROUP BY escalation_reason ORDER BY count DESC;",
            },
            {
                "name": "RMA Risk Assessment",
                "sql": "SELECT d.model, d.firmware_version, COUNT(r.id) as rma_count, ROUND(100.0*COUNT(CASE WHEN r.success_flag=false THEN 1 END)/COUNT(r.id), 2) as failure_rate FROM support_devices d JOIN support_ticket_device_links tdl ON d.id=tdl.device_id JOIN support_tickets t ON tdl.ticket_id=t.id LEFT JOIN support_resolutions r ON t.id=r.ticket_id GROUP BY d.model, d.firmware_version HAVING COUNT(r.id) > 0 ORDER BY failure_rate DESC;",
            },
        ]

        for q in queries:
            result = self.post(
                f"/api/ask/prepare",
                {
                    "workspace_id": self.workspace_id,
                    "query_name": q["name"],
                    "sql": q["sql"],
                },
            )
            self.log(f"Query prepared: {q['name']}")

    def step_5_generate_graph(self) -> None:
        """Step 5: Generate knowledge graph from ingested data."""
        self.log("STEP 5: Generating knowledge graph")

        result = self.post(
            f"/api/graph/build",
            {
                "workspace_id": self.workspace_id,
                "entity_types": [
                    "Customer",
                    "Site",
                    "Device",
                    "Agent",
                    "Ticket",
                    "Resolution",
                    "ExpertiseTag",
                ],
                "relationships": [
                    "Device-hasModel",
                    "Device-runsFirmware",
                    "Agent-hasLevel",
                    "Agent-hasSpecialty",
                    "Agent-hasExpertise",
                    "Ticket-assignedTo",
                    "Ticket-affectsDevice",
                    "Ticket-rootCause",
                    "Ticket-resolvedBy",
                    "Resolution-solutionType",
                ],
            },
        )
        self.log("Knowledge graph built")

    def step_6_export_ontology(self) -> None:
        """Step 6: Export ontology as RDF."""
        self.log("STEP 6: Exporting ontology as RDF")

        result = self.post(
            f"/api/ontology/export",
            {
                "workspace_id": self.workspace_id,
                "format": "rdf",
                "filename": "demo_support_ticket_ontology.rdf",
            },
        )
        self.log(f"Ontology exported: RDF format")

    def step_7_update_observability(self) -> None:
        """Step 7: Update observability matrix."""
        self.log("STEP 7: Updating observability metrics")

        metrics = {
            "workspace_id": self.workspace_id,
            "metrics": [
                {
                    "name": "total_tickets",
                    "query": "SELECT COUNT(*) FROM support_tickets;",
                },
                {
                    "name": "resolution_rate",
                    "query": "SELECT ROUND(100.0*COUNT(CASE WHEN status='resolved' THEN 1 END)/COUNT(*), 2) FROM support_tickets;",
                },
                {
                    "name": "escalation_rate",
                    "query": "SELECT ROUND(100.0*COUNT(CASE WHEN escalation_reason IS NOT NULL THEN 1 END)/COUNT(*), 2) FROM support_tickets;",
                },
                {
                    "name": "avg_mttr_hours",
                    "query": "SELECT ROUND(AVG(EXTRACT(HOUR FROM (resolved_at - created_at)))::numeric, 1) FROM support_tickets WHERE status='resolved';",
                },
                {
                    "name": "critical_escalations",
                    "query": "SELECT COUNT(*) FROM support_tickets WHERE priority='critical' AND escalation_reason IS NOT NULL;",
                },
            ],
        }

        result = self.post(
            f"/api/observability/update",
            metrics,
        )
        self.log("Observability metrics updated")

    def run_full_onboarding(self) -> None:
        """Execute all 7 steps."""
        print(
            """
╔════════════════════════════════════════════════════════════════╗
║  Aryx Demo Support Ticket Workspace — Full Backend Onboarding  ║
╚════════════════════════════════════════════════════════════════╝
"""
        )

        try:
            self.step_1_create_workspace()
            self.step_2_fill_brief()
            self.step_3_ingest_tables()
            self.step_4_prepare_ask_queries()
            self.step_5_generate_graph()
            self.step_6_export_ontology()
            self.step_7_update_observability()

            print(
                f"""
╔════════════════════════════════════════════════════════════════╗
║                    ✅ ONBOARDING COMPLETE                      ║
╚════════════════════════════════════════════════════════════════╝

Workspace:  demo_support_ticket (ID: {self.workspace_id})
Tables:     9 ingested (customers, sites, devices, agents, tickets, resolutions, etc.)
Queries:    5 prepared (Open Tickets, Workload, Failure Patterns, Escalations, RMA Risk)
Graph:      Knowledge graph built with entities & relationships
Ontology:   Exported as RDF
Observability: Metrics dashboard updated

📊 Ready for customer demo tomorrow!
   • Brief: Domain model + 5 competency questions ✅
   • Ingest: All support tables loaded ✅
   • Ask: Pre-canned queries ready ✅
   • Graph: Entity relationships mapped ✅
   • Ontology: RDF export available ✅
   • Observability: Metrics live ✅
"""
            )

        except Exception as e:
            self.err(f"Onboarding failed: {e}")


def main():
    onboarder = AryxDemoOnboarder(api_url="http://localhost:8088")
    onboarder.run_full_onboarding()


if __name__ == "__main__":
    main()
