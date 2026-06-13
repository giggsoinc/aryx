{ddl_verb} {table} (
  source_id BIGINT NOT NULL,
  target_id BIGINT NOT NULL,
  PRIMARY KEY (source_id, target_id)
);
