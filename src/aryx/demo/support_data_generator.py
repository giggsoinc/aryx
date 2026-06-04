"""Synthetic data generator for support demo — 200 realistic radio support tickets."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

# Realistic radio equipment support vocabulary
CUSTOMERS = [
    ("NetOps Atlantic", "platinum"),
    ("Regional Wireless Co", "gold"),
    ("Metro Telecom", "gold"),
    ("Rural Comms Group", "silver"),
    ("Emergency Services Net", "platinum"),
    ("Industrial IoT Ops", "silver"),
    ("Federal Communications", "platinum"),
    ("Regional TV Broadcast", "gold"),
    ("Enterprise Mobility", "gold"),
    ("Utility Company A", "silver"),
]

SITES = {
    "HQ": ["New York", "Los Angeles", "Chicago", "Denver", "Atlanta"],
    "Remote": ["Seattle", "Phoenix", "Miami", "Boston", "Dallas", "San Francisco"],
    "Mobile": ["Unit-Mobile-01", "Unit-Mobile-02", "Unit-Mobile-03", "Unit-Mobile-04"],
}

DEVICE_MODELS = [
    "RadioX-6000", "RadioX-7000", "RadioX-9000",
    "WaveLink-200", "WaveLink-400", "WaveLink-600",
    "SectorMaster-2500", "SectorMaster-3000",
    "FieldOps-1000", "FieldOps-2000",
]

FIRMWARE_VERSIONS = ["6.2.1", "6.2.3", "6.3.0", "6.3.2", "7.0.0", "7.0.1"]

AGENTS = [
    ("Alex Chen", "L3", "Firmware"),
    ("Jordan Martinez", "L3", "Hardware"),
    ("Sam Patel", "L2", "Firmware"),
    ("Casey Brown", "L2", "Network"),
    ("Morgan Lee", "L2", "Configuration"),
    ("Taylor White", "L1", "General"),
    ("Riley Johnson", "L1", "General"),
    ("Alex Kim", "L1", "General"),
    ("Jordan Davis", "L2", "Hardware"),
    ("Casey Garcia", "L1", "General"),
    ("Morgan Wilson", "L3", "Network"),
    ("Taylor Anderson", "L2", "Configuration"),
    ("Riley Thomas", "L1", "General"),
    ("Alex Rodriguez", "L2", "Firmware"),
    ("Jordan Lopez", "L1", "General"),
]

EXPERTISE_TAGS = [
    "Firmware-6.2",
    "Firmware-7.0",
    "RMA-eligible",
    "Power-management",
    "Network-interference",
    "Configuration-advanced",
    "Hardware-debugging",
    "Field-certified",
]

SYMPTOMS = [
    "Device intermittent loss of signal",
    "Firmware crashes on boot",
    "Configuration memory corruption detected",
    "Network interface degradation",
    "Power supply instability",
    "Thermal shutdown triggered",
    "Cannot establish link with peer device",
    "Intermittent packet loss on uplink",
    "Device unresponsive to commands",
    "Frequent automatic reboot cycle",
    "Firmware update failed, device in recovery mode",
    "Radio frequency interference detected",
    "Device locked after failed authentication",
    "Memory usage spike, process crash",
    "Incorrect firmware version reported",
    "Device shows wrong configuration hash",
    "Cannot connect to management interface",
    "High CRC error rate on receive",
    "Backup power not activating",
    "Device reporting phantom alarms",
]

SOLUTION_TYPES = [
    "firmware_update",
    "config_push",
    "rma",
    "reboot",
    "documentation",
    "escalation",
]

KB_ARTICLES = [
    "https://kb.example.com/firmware-6.2-known-issues",
    "https://kb.example.com/thermal-management",
    "https://kb.example.com/network-tuning",
    "https://kb.example.com/rma-procedures",
    "https://kb.example.com/power-diagnostics",
    "https://kb.example.com/firmware-migration",
    "https://kb.example.com/interference-mitigation",
    "https://kb.example.com/device-recovery",
]


class SupportDataGenerator:
    """Generate realistic radio support ticket data."""

    def __init__(self, ticket_count: int = 200, seed: int | None = None):
        self.ticket_count = ticket_count
        if seed:
            random.seed(seed)
        self.now = datetime.utcnow()

    def generate_customers(self) -> list[dict[str, Any]]:
        """Generate 10 customers."""
        return [
            {
                "name": name,
                "sla_tier": tier,
                "primary_contact": f"contact@{name.lower().replace(' ', '')}.com",
                "created_at": self.now - timedelta(days=random.randint(30, 365)),
            }
            for name, tier in CUSTOMERS
        ]

    def generate_sites(self, customer_ids: list[int]) -> list[dict[str, Any]]:
        """Generate ~20 sites across customers."""
        sites = []
        for cid in customer_ids:
            site_types = list(SITES.keys())
            for _ in range(random.randint(1, 3)):
                site_type = random.choice(site_types)
                location = random.choice(SITES[site_type])
                sites.append({
                    "customer_id": cid,
                    "location": location,
                    "site_type": site_type,
                    "device_count": random.randint(5, 50),
                    "created_at": self.now - timedelta(days=random.randint(10, 365)),
                })
        return sites

    def generate_devices(self, site_ids: list[int]) -> list[dict[str, Any]]:
        """Generate ~150 devices across sites."""
        devices = []
        for sid in site_ids:
            count = random.randint(5, 20)
            for _ in range(count):
                devices.append({
                    "site_id": sid,
                    "model": random.choice(DEVICE_MODELS),
                    "firmware_version": random.choice(FIRMWARE_VERSIONS),
                    "config_hash": f"sha256_{random.randint(1000, 9999):04d}",
                    "install_date": (
                        self.now - timedelta(days=random.randint(30, 1000))
                    ).date(),
                    "status": random.choices(
                        ["active", "inactive", "degraded", "rma"],
                        weights=[70, 10, 15, 5],
                    )[0],
                    "last_heartbeat": (
                        self.now - timedelta(minutes=random.randint(1, 1440))
                        if random.random() > 0.2
                        else None
                    ),
                    "created_at": self.now - timedelta(days=random.randint(10, 365)),
                })
        return devices

    def generate_agents(self) -> list[dict[str, Any]]:
        """Generate 15 support agents."""
        return [
            {
                "name": name,
                "level": level,
                "specialty": specialty,
                "max_concurrent_tickets": 3 if level == "L3" else 5,
                "tickets_resolved": random.randint(10, 200),
                "created_at": self.now - timedelta(days=random.randint(30, 730)),
            }
            for name, level, specialty in AGENTS
        ]

    def generate_expertise_tags(self) -> list[dict[str, Any]]:
        """Generate expertise tags."""
        return [
            {"tag_name": tag, "description": f"Expertise in {tag}"}
            for tag in EXPERTISE_TAGS
        ]

    def generate_tickets(self, site_ids: list[int], agent_ids: list[int]
                        ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Generate 200 tickets + device links."""
        tickets = []
        links = []

        for i in range(self.ticket_count):
            site_id = random.choice(site_ids)
            priority = random.choices(
                ["low", "medium", "high", "critical"],
                weights=[20, 40, 30, 10],
            )[0]

            # Escalation logic: critical/high more likely to escalate
            escalate = (
                priority in ["critical", "high"]
                and random.random() < (0.7 if priority == "critical" else 0.4)
            )

            status = random.choices(
                ["open", "in_progress", "escalated", "resolved", "closed"],
                weights=[15, 25, (35 if escalate else 5), 20, 10],
            )[0]

            days_ago = random.randint(1, 90)
            created = self.now - timedelta(days=days_ago, hours=random.randint(0, 23))
            resolved = (
                created + timedelta(hours=random.randint(2, 48))
                if status in ["resolved", "closed"]
                else None
            )

            ticket = {
                "site_id": site_id,
                "created_by": f"user_{random.randint(1, 50)}@customer.com",
                "assigned_agent_id": random.choice(agent_ids) if random.random() > 0.1 else None,
                "status": status,
                "priority": priority,
                "symptom_text": random.choice(SYMPTOMS),
                "resolution_notes": (
                    "Resolved via firmware update" if status == "resolved"
                    else "Escalated to L3" if status == "escalated"
                    else None
                ),
                "resolved_at": resolved,
                "escalation_reason": (
                    "Hardware diagnostics inconclusive" if escalate
                    else None
                ),
                "created_at": created,
                "updated_at": resolved or created,
            }
            tickets.append(ticket)

            # Generate device links: 1–3 devices per ticket
            link_count = random.randint(1, 3)
            devices_for_site = [sid for sid, s_id in enumerate(site_ids) if s_id == site_id]
            # We'll set device_ids in a second pass after we know them
            # For now, store placeholder
            for _ in range(link_count):
                links.append({
                    "ticket_index": i,
                    "device_role": random.choice(["affected", "root_cause", "witness"]),
                })

        return tickets, links

    def generate_resolutions(self, ticket_count: int) -> list[dict[str, Any]]:
        """Generate resolution records for resolved tickets."""
        resolutions = []
        for ticket_id in range(1, ticket_count + 1):
            if random.random() < 0.6:  # 60% of tickets get a resolution
                solution_type = random.choice(SOLUTION_TYPES)
                resolutions.append({
                    "ticket_id": ticket_id,
                    "solution_type": solution_type,
                    "applied_by_agent_id": random.randint(1, 15),
                    "knowledge_link": (
                        random.choice(KB_ARTICLES)
                        if random.random() > 0.3
                        else None
                    ),
                    "success_flag": random.random() > 0.2,
                    "created_at": self.now - timedelta(days=random.randint(1, 30)),
                })
        return resolutions
