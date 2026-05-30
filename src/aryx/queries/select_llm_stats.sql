SELECT count(*) AS total_calls,
       coalesce(sum(prompt_tokens + completion_tokens), 0) AS total_tokens,
       coalesce(avg(latency_ms)::int, 0) AS avg_latency_ms,
       coalesce(sum(prompt_tokens), 0) AS prompt_tokens,
       coalesce(sum(completion_tokens), 0) AS completion_tokens
FROM aryx_llm_call
