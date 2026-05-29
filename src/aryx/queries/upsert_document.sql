INSERT INTO aryx_document (content_hash, file_name, source_type, byte_count)
VALUES (%s, %s, %s, %s)
ON CONFLICT (content_hash) DO UPDATE SET file_name = EXCLUDED.file_name
RETURNING id
