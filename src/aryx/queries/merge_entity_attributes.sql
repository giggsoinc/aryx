UPDATE aryx_entity dst
SET attributes = src.attributes || dst.attributes
FROM aryx_entity src
WHERE dst.id = %s AND dst.workspace_id = %s
  AND src.id = %s AND src.workspace_id = %s
