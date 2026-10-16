SELECT DATABASE() AS current_database, VERSION() AS mysql_version;

SELECT COUNT(*) AS agent_run_table_count
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'agent_run';

SELECT table_name AS conflicting_table
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
  )
ORDER BY table_name;
