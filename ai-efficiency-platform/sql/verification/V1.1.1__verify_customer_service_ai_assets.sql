SELECT agent_key, status
FROM ai_agent_definition
WHERE id = '10000000-0000-0000-0000-000000000001';

SELECT scope, COUNT(*) AS definition_count,
       SUM(owner_agent_definition_id IS NULL) AS owner_is_null_count
FROM ai_prompt_definition
WHERE id BETWEEN '20000000-0000-0000-0000-000000000001'
             AND '20000000-0000-0000-0000-000000000015'
GROUP BY scope
ORDER BY scope;

SELECT COUNT(*) AS published_prompt_versions
FROM ai_prompt_version
WHERE id BETWEEN '30000000-0000-0000-0000-000000000001'
             AND '30000000-0000-0000-0000-000000000015'
  AND status = 'PUBLISHED';

SELECT COUNT(*) AS user_templates,
       SUM(trusted_instruction = 0) AS untrusted_user_templates
FROM ai_prompt_message_template
WHERE role = 'USER'
  AND prompt_version_id BETWEEN '30000000-0000-0000-0000-000000000001'
                            AND '30000000-0000-0000-0000-000000000015';

SELECT COUNT(*) AS untrusted_runtime_variables
FROM ai_prompt_variable
WHERE value_source = 'RUNTIME_INPUT'
  AND allow_untrusted_content = 1;

SELECT policy_key, status FROM ai_model_policy
WHERE id = '12000000-0000-0000-0000-000000000001';

SELECT policy_key, status FROM ai_rag_policy
WHERE id = '13000000-0000-0000-0000-000000000001';
