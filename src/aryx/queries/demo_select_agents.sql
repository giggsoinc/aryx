SELECT id, name, level, specialty, tickets_resolved
FROM support_agents
WHERE (CAST(:level AS TEXT) IS NULL OR level = :level)
ORDER BY level DESC, tickets_resolved DESC
