-- Raw attribute map (status, priority, amount, ...) for a set of entities.
SELECT id, attributes
FROM aryx_entity
WHERE workspace_id = %(ws)s AND id = ANY(%(ids)s)
