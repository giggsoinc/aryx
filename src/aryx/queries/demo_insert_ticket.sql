INSERT INTO support_tickets (site_id, created_by, assigned_agent_id, status,
                             priority, symptom_text, resolution_notes,
                             resolved_at, escalation_reason, created_at, updated_at)
VALUES (:site_id, :created_by, :assigned_agent_id, :status,
        :priority, :symptom_text, :resolution_notes,
        :resolved_at, :escalation_reason, :created_at, :updated_at)
