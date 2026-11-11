SELECT EXISTS (
    SELECT 1
      FROM aryx_entity_member m
      JOIN aryx_landed_record l
        ON l.id = m.landed_record_id AND l.workspace_id = m.workspace_id
     WHERE m.workspace_id = %s
       AND l.source_dataset = %s
)
