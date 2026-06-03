INSERT INTO aryx_ask_history (
    workspace_id, question, answer, tools_called, entity_ids,
    prompt_tokens, completion_tokens, latency_ms, answer_model
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id, asked_at
