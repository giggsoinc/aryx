INSERT INTO aryx_chunk (doc_id, chunk_index, page_slide, char_start, char_end, text)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (doc_id, chunk_index) DO NOTHING
RETURNING id
