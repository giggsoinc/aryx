-- Factory reset: truncate every data table, reset workspace to Default only.
-- Partition children must be truncated directly (TRUNCATE on parent cascades).
TRUNCATE
  aryx_action_execution, aryx_action,
  aryx_adjudication, aryx_attribute_conflict,
  aryx_ask_history, aryx_axiom_violation,
  aryx_projected_entity, aryx_projection_state,
  aryx_ontology_axiom, aryx_ontology_change_log,
  aryx_ontology_rule, aryx_ontology_type, aryx_ontology_version,
  aryx_run_stage, aryx_match_edge, aryx_block_done, aryx_block_member,
  aryx_run,
  aryx_job_event, aryx_job_archive, aryx_job,
  aryx_chunk_embedding, aryx_chunk, aryx_document,
  aryx_field_profile, aryx_field_tag,
  aryx_llm_call, aryx_schema_mapping, aryx_mcp_token
CASCADE;
