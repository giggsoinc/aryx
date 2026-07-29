INSERT INTO aryx_planning_context
    (workspace_id, planning_context_id, dataset_id, dataset_version,
     context_status, approved_columns, context)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id, dataset_version) DO UPDATE SET
    planning_context_id = EXCLUDED.planning_context_id,
    context_status      = EXCLUDED.context_status,
    approved_columns    = EXCLUDED.approved_columns,
    context             = EXCLUDED.context,
    created_at          = NOW()
