UPDATE aryx_action
SET superseded_by = %s
WHERE workspace_id = %s AND name = %s
  AND superseded_by IS NULL AND id <> %s
