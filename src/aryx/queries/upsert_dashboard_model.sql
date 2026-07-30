INSERT INTO aryx_dashboard_model
    (workspace_id, dashboard_model_id, spec_id, dataset_id, dataset_version,
     section_count, composition_status, composed_by, model)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id, dataset_version) DO UPDATE SET
    dashboard_model_id  = EXCLUDED.dashboard_model_id,
    spec_id             = EXCLUDED.spec_id,
    section_count       = EXCLUDED.section_count,
    composition_status  = EXCLUDED.composition_status,
    composed_by         = EXCLUDED.composed_by,
    model               = EXCLUDED.model,
    created_at          = NOW()
