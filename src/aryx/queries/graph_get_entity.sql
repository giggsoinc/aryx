SELECT id, ontology_type, aryx_display_name(attributes, id) AS name
FROM aryx_entity
WHERE workspace_id = %(ws)s AND id = %(id)s
