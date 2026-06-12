SELECT id, ticket_id, solution_type, success_flag, created_at
FROM support_resolutions
WHERE ticket_id = :ticket_id
ORDER BY created_at
