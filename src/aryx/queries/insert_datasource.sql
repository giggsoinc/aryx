INSERT INTO aryx_datasource
    (workspace_id, name, kind, config_json, secret_cipher, secret_mask)
VALUES (%(workspace_id)s, %(name)s, %(kind)s,
        %(config_json)s::jsonb, %(secret_cipher)s, %(secret_mask)s)
RETURNING id, workspace_id, name, kind, config_json, secret_mask, created_at
