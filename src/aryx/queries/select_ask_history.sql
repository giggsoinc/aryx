SELECT id, workspace_id, asked_at, question, answer, tools_called,
       entity_ids, prompt_tokens, completion_tokens, latency_ms, answer_model
FROM aryx_ask_history
WHERE workspace_id = %s
ORDER BY asked_at DESC
LIMIT %s
