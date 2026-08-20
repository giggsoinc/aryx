SELECT
    count(*) FILTER (WHERE status = 'pending')                      AS pending,
    count(*) FILTER (WHERE status = 'approved')                     AS approved,
    count(*) FILTER (WHERE status = 'rejected')                     AS rejected,
    count(*) FILTER (WHERE status = 'auto_llm')                     AS auto_llm,
    count(*) FILTER (WHERE status IN ('approved', 'rejected')
                     AND llm_verdict IS NOT NULL
                     AND llm_verdict = (status = 'approved'))       AS human_llm_agree,
    count(*) FILTER (WHERE status IN ('approved', 'rejected')
                     AND llm_verdict IS NOT NULL)                   AS human_llm_overlap
FROM aryx_adjudication
WHERE workspace_id = %s
