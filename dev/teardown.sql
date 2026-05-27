-- DEV ONLY — fully reverses dev/seed.sql and purges its validation runs.
-- Deletions are intentional and scoped strictly to demo data.
-- When committing or running under Raven, tag: [GUARD:ALLOW-DELETE]

-- 1. Remove landed artifacts produced by validation runs over the demo source
--    (profiles and records reference aryx_run, so clear them before the runs).
DELETE FROM aryx_field_profile
 WHERE run_id IN (
     SELECT run_id FROM aryx_run WHERE source_dataset = 'demo_customers'
 );

DELETE FROM aryx_landed_record
 WHERE source_dataset = 'demo_customers';

DELETE FROM aryx_run
 WHERE source_dataset = 'demo_customers';

-- 2. Remove the synthetic source table itself.
DROP TABLE IF EXISTS demo_customers;
