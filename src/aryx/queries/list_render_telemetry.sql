SELECT render_id, dashboard_model_id, render_status, rendered_component_count,
       warning_count, unsupported_component_types, accessibility_checks, created_at
FROM aryx_render_telemetry
WHERE workspace_id = %s AND dashboard_model_id = %s
ORDER BY created_at DESC
LIMIT %s
