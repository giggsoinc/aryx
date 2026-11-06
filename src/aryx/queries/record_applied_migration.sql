INSERT INTO aryx_schema_migration (filename) VALUES (%s)
ON CONFLICT (filename) DO NOTHING
