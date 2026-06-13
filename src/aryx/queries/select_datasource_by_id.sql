SELECT id, workspace_id, name, kind, config_json, secret_cipher, secret_mask, created_at
FROM aryx_datasource
WHERE id = %(id)s
