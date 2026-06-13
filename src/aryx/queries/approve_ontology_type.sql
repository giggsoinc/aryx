UPDATE aryx_ontology_type
   SET status = 'approved'
 WHERE workspace_id = %s AND name = %s
