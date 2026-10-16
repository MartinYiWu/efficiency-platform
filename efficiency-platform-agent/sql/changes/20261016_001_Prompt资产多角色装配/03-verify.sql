SELECT COUNT(*) AS prompt_table_count
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
    'agent_prompt_definition',
    'agent_prompt_version',
    'agent_prompt_message_template',
    'agent_prompt_variable',
    'agent_model_policy',
    'agent_output_contract',
    'agent_prompt_release',
    'agent_run_prompt_snapshot',
    'agent_prompt_test_case'
  );

SELECT table_name, index_name, non_unique
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN (
    'agent_prompt_definition',
    'agent_prompt_version',
    'agent_prompt_message_template',
    'agent_prompt_variable',
    'agent_model_policy',
    'agent_output_contract',
    'agent_prompt_release',
    'agent_run_prompt_snapshot',
    'agent_prompt_test_case'
  )
  AND non_unique = 0
ORDER BY table_name, index_name;

SELECT COUNT(*) AS release_definition_mismatch_count
FROM agent_prompt_release release_record
JOIN agent_prompt_version version_record
  ON version_record.id = release_record.prompt_version_id
WHERE version_record.prompt_definition_id <> release_record.prompt_definition_id;

SELECT COUNT(*) AS orphan_message_count
FROM agent_prompt_message_template message_record
LEFT JOIN agent_prompt_version version_record
  ON version_record.id = message_record.prompt_version_id
WHERE version_record.id IS NULL;

SELECT COUNT(*) AS orphan_variable_count
FROM agent_prompt_variable variable_record
LEFT JOIN agent_prompt_message_template message_record
  ON message_record.id = variable_record.prompt_message_template_id
WHERE message_record.id IS NULL;

SELECT COUNT(*) AS orphan_snapshot_count
FROM agent_run_prompt_snapshot snapshot_record
LEFT JOIN agent_run run_record ON run_record.run_id = snapshot_record.run_id
LEFT JOIN agent_prompt_version version_record
  ON version_record.id = snapshot_record.prompt_version_id
LEFT JOIN agent_model_policy model_record
  ON model_record.id = snapshot_record.model_policy_id
LEFT JOIN agent_output_contract contract_record
  ON contract_record.id = snapshot_record.output_contract_id
WHERE run_record.run_id IS NULL
   OR version_record.id IS NULL
   OR model_record.id IS NULL
   OR contract_record.id IS NULL;

SELECT COUNT(*) AS invalid_trusted_role_count
FROM agent_prompt_message_template
WHERE trusted_instruction = 1
  AND role NOT IN ('system', 'developer');

SELECT COUNT(*) AS invalid_untrusted_variable_count
FROM agent_prompt_variable variable_record
JOIN agent_prompt_message_template message_record
  ON message_record.id = variable_record.prompt_message_template_id
WHERE message_record.role IN ('system', 'developer')
  AND (
    variable_record.value_source <> 'system_context'
    OR variable_record.allow_untrusted_content <> 0
  );
