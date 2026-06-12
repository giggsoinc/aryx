INSERT INTO support_agents (name, level, specialty, max_concurrent_tickets,
                            tickets_resolved, created_at)
VALUES (:name, :level, :specialty, :max_concurrent_tickets,
        :tickets_resolved, :created_at)
