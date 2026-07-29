SELECT EXISTS(
    SELECT 1 FROM aryx_user_intent
    WHERE workspace_id = %s AND validation_status = 'valid'
)
