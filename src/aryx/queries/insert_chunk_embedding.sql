INSERT INTO aryx_chunk_embedding (chunk_id, model_id, dim, embedding)
VALUES (%s, %s, %s, %s::vector)
ON CONFLICT (chunk_id, model_id) DO NOTHING
