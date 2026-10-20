SELECT b.agent_version_id, m.policy_key AS model_policy_key, r.policy_key AS rag_policy_key
FROM ai_agent_version_policy_binding b
JOIN ai_model_policy m ON m.id = b.model_policy_id
JOIN ai_rag_policy r ON r.id = b.rag_policy_id
WHERE b.agent_version_id = '11000000-0000-0000-0000-000000000001';
