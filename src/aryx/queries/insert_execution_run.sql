INSERT INTO aryx_execution_run
    (workspace_id, execution_run_id, execution_plan_id, spec_id, dataset_id,
     dataset_version, status, kpi_count, analysis_count, run)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
