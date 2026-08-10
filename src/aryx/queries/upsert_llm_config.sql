INSERT INTO aryx_llm_config (id, provider, menial_model, answer_model, endpoint, api_key)
VALUES (1, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    provider = EXCLUDED.provider,
    menial_model = EXCLUDED.menial_model,
    answer_model = EXCLUDED.answer_model,
    endpoint = EXCLUDED.endpoint,
    api_key = EXCLUDED.api_key,
    updated_at = now()
