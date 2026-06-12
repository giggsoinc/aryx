UPDATE aryx_workspace
SET context = '', brief = '{}'::jsonb, survivorship = '{}'::jsonb
WHERE id = %(wid)s
