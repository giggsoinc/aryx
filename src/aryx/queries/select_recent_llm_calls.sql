SELECT role, model, prompt_tokens, completion_tokens, latency_ms, source, error, ts
FROM aryx_llm_call
ORDER BY ts DESC
LIMIT 50
