-- Support ticket demo schema for Aryx onboarding
-- Tables: customers, sites, devices, agents, tickets, resolutions, and many-to-many links

CREATE TABLE IF NOT EXISTS support_customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    sla_tier VARCHAR(50) NOT NULL CHECK (sla_tier IN ('bronze', 'silver', 'gold', 'platinum')),
    primary_contact VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_sites (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES support_customers(id) ON DELETE CASCADE,
    location VARCHAR(255) NOT NULL,
    site_type VARCHAR(50) NOT NULL CHECK (site_type IN ('HQ', 'Remote', 'Mobile')),
    device_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_devices (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES support_sites(id) ON DELETE CASCADE,
    model VARCHAR(100) NOT NULL,
    firmware_version VARCHAR(50) NOT NULL,
    config_hash VARCHAR(64),
    install_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('active', 'inactive', 'degraded', 'rma')),
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    level VARCHAR(10) NOT NULL CHECK (level IN ('L1', 'L2', 'L3')),
    specialty VARCHAR(100) NOT NULL CHECK (specialty IN ('Hardware', 'Firmware', 'Network', 'Configuration', 'General')),
    max_concurrent_tickets INTEGER DEFAULT 5,
    tickets_resolved INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_expertise_tags (
    id SERIAL PRIMARY KEY,
    tag_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_agent_expertise (
    agent_id INTEGER NOT NULL REFERENCES support_agents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES support_expertise_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, tag_id)
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES support_sites(id) ON DELETE CASCADE,
    created_by VARCHAR(255) NOT NULL,
    assigned_agent_id INTEGER REFERENCES support_agents(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('open', 'in_progress', 'escalated', 'resolved', 'closed')),
    priority VARCHAR(20) NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    symptom_text TEXT NOT NULL,
    resolution_notes TEXT,
    resolved_at TIMESTAMP,
    escalation_reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_ticket_device_links (
    ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES support_devices(id) ON DELETE CASCADE,
    device_role VARCHAR(50) NOT NULL CHECK (device_role IN ('affected', 'root_cause', 'witness')),
    PRIMARY KEY (ticket_id, device_id, device_role)
);

CREATE TABLE IF NOT EXISTS support_resolutions (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    solution_type VARCHAR(100) NOT NULL CHECK (solution_type IN ('firmware_update', 'config_push', 'rma', 'reboot', 'documentation', 'escalation')),
    applied_by_agent_id INTEGER REFERENCES support_agents(id) ON DELETE SET NULL,
    knowledge_link TEXT,
    success_flag BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indices for performance (demo + production)
CREATE INDEX idx_support_sites_customer_id ON support_sites(customer_id);
CREATE INDEX idx_support_devices_site_id ON support_devices(site_id);
CREATE INDEX idx_support_devices_status ON support_devices(status);
CREATE INDEX idx_support_tickets_site_id ON support_tickets(site_id);
CREATE INDEX idx_support_tickets_assigned_agent_id ON support_tickets(assigned_agent_id);
CREATE INDEX idx_support_tickets_status ON support_tickets(status);
CREATE INDEX idx_support_tickets_priority ON support_tickets(priority);
CREATE INDEX idx_support_ticket_device_links_ticket_id ON support_ticket_device_links(ticket_id);
CREATE INDEX idx_support_ticket_device_links_device_id ON support_ticket_device_links(device_id);
CREATE INDEX idx_support_resolutions_ticket_id ON support_resolutions(ticket_id);
CREATE INDEX idx_support_agent_expertise_agent_id ON support_agent_expertise(agent_id);
