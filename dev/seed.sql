-- DEV ONLY — synthetic source data for end-to-end validation.
-- NOT copied into the worker image (Dockerfile copies src/ only) and never
-- run in production. Fully reversible via dev/teardown.sql.
--
-- Simulates an upstream source table the PostgresConnector extracts from.
-- Blank/whitespace emails (rows 3, 5) deliberately exercise the clean() stage.

CREATE TABLE IF NOT EXISTS demo_customers (
    id        INTEGER PRIMARY KEY,
    full_name TEXT,
    email     TEXT,
    country   TEXT,
    signed_up DATE
);

INSERT INTO demo_customers (id, full_name, email, country, signed_up) VALUES
    (1, 'Acme Corp',        'ap@acme.example',       'US', '2024-01-15'),
    (2, 'Globex LLC',       'billing@globex.example','US', '2024-03-02'),
    (3, 'Initech',          '',                      'CA', '2024-05-20'),
    (4, 'Umbrella Co',      'finance@umbrella.example','GB','2024-06-11'),
    (5, 'Stark Industries', '   ',                   'US', '2024-07-30')
ON CONFLICT (id) DO NOTHING;
