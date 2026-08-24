SELECT id, left_record_id, right_record_id
FROM aryx_adjudication
WHERE workspace_id = %s AND status = 'pending' AND id != %s
