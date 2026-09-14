SELECT EXISTS(
    SELECT 1 FROM aryx_landed_record
    WHERE workspace_id = %s AND source_system = 'document'
) AS has_documents
