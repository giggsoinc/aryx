INSERT INTO aryx_execution_plan
    (workspace_id, execution_plan_id, spec_id, dataset_id, dataset_version,
     node_count, compilation_status, plan)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id, dataset_version) DO UPDATE SET
    execution_plan_id  = EXCLUDED.execution_plan_id,
    spec_id            = EXCLUDED.spec_id,
    node_count         = EXCLUDED.node_count,
    compilation_status = EXCLUDED.compilation_status,
    plan               = EXCLUDED.plan,
    created_at         = NOW()
