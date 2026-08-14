INSERT INTO aryx_dashboard_spec
    (workspace_id, spec_id, dataset_id, dataset_version, status, error_code,
     kpi_count, warning_count, result)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id, dataset_version) DO UPDATE SET
    spec_id       = EXCLUDED.spec_id,
    status        = EXCLUDED.status,
    error_code    = EXCLUDED.error_code,
    kpi_count     = EXCLUDED.kpi_count,
    warning_count = EXCLUDED.warning_count,
    result        = EXCLUDED.result,
    created_at    = NOW()
