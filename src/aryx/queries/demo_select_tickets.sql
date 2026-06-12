SELECT id, site_id, status, priority, symptom_text, assigned_agent_id,
       created_at, resolved_at
FROM support_tickets
WHERE (CAST(:status AS TEXT) IS NULL OR status = :status)
  AND (CAST(:priority AS TEXT) IS NULL OR priority = :priority)
ORDER BY created_at DESC
LIMIT 100
