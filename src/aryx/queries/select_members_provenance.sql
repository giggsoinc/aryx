SELECT m.entity_id, l.source_system, l.source_dataset, l.source_record_id
FROM aryx_entity_member m
JOIN aryx_landed_record l ON l.id = m.landed_record_id
