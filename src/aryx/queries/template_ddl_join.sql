-- Join-table DDL template for relationship export (Slice 4).
-- {table} = sanitised relationship name.
{ddl_verb} {table} (
  source_id BIGINT NOT NULL,
  target_id BIGINT NOT NULL,
  PRIMARY KEY (source_id, target_id)
);
