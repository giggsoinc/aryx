INSERT INTO aryx_graph_version
    (workspace_id, graph_id, version, content_hash, dataset_ids, entity_count,
     relationship_count, duplicate_entities, duplicate_relationships,
     dangling_relationships, schema_status, normalized_graph_ref,
     graph_json, normalized, report)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
