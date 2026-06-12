INSERT INTO support_resolutions (ticket_id, solution_type, applied_by_agent_id,
                                 knowledge_link, success_flag, created_at, updated_at)
VALUES (:ticket_id, :solution_type, :applied_by_agent_id,
        :knowledge_link, :success_flag, :created_at, CURRENT_TIMESTAMP)
