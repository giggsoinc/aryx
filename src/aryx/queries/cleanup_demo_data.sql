-- Clean demo support data (reverse dependency order)
DELETE FROM support_resolutions;
DELETE FROM support_ticket_device_links;
DELETE FROM support_tickets;
DELETE FROM support_agent_expertise;
DELETE FROM support_expertise_tags;
DELETE FROM support_agents;
DELETE FROM support_devices;
DELETE FROM support_sites;
DELETE FROM support_customers;
