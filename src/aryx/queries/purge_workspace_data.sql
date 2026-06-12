-- Purge all data for one workspace. Caller passes %(wid)s.
-- Order: children before parents to respect FK constraints.
DELETE FROM aryx_action_execution WHERE workspace_id = %(wid)s;
DELETE FROM aryx_action WHERE workspace_id = %(wid)s;
DELETE FROM aryx_adjudication WHERE workspace_id = %(wid)s;
DELETE FROM aryx_attribute_conflict WHERE workspace_id = %(wid)s;
DELETE FROM aryx_ask_history WHERE workspace_id = %(wid)s;
DELETE FROM aryx_axiom_violation WHERE workspace_id = %(wid)s;
DELETE FROM aryx_projected_entity WHERE workspace_id = %(wid)s;
DELETE FROM aryx_projection_state WHERE workspace_id = %(wid)s;
DELETE FROM aryx_ontology_axiom WHERE workspace_id = %(wid)s;
DELETE FROM aryx_ontology_change_log WHERE workspace_id = %(wid)s;
DELETE FROM aryx_ontology_rule WHERE workspace_id = %(wid)s;
DELETE FROM aryx_ontology_version WHERE workspace_id = %(wid)s;
DELETE FROM aryx_run_stage WHERE run_id IN (SELECT id FROM aryx_run WHERE workspace_id = %(wid)s);
DELETE FROM aryx_match_edge WHERE run_id IN (SELECT id FROM aryx_run WHERE workspace_id = %(wid)s);
DELETE FROM aryx_block_done WHERE run_id IN (SELECT id FROM aryx_run WHERE workspace_id = %(wid)s);
DELETE FROM aryx_block_member WHERE run_id IN (SELECT id FROM aryx_run WHERE workspace_id = %(wid)s);
DELETE FROM aryx_run WHERE workspace_id = %(wid)s;
DELETE FROM aryx_job_event WHERE job_id IN (SELECT id FROM aryx_job WHERE workspace_id = %(wid)s);
DELETE FROM aryx_job WHERE workspace_id = %(wid)s;
