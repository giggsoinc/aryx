INSERT INTO aryx_render_telemetry
    (workspace_id, render_id, dashboard_model_id, render_status,
     rendered_component_count, warning_count, unsupported_component_types,
     accessibility_checks)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
