-- 只读预检：全部目标表应不存在；不读取简历正文、不写DDL。
SELECT VERSION() AS database_version,DATABASE() AS target_database;
SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_hr_position_sequence','ai_hr_position','ai_hr_position_draft','ai_hr_config_version','ai_hr_candidate','ai_hr_fact_snapshot','ai_hr_semantic_snapshot','ai_hr_matching_run','ai_hr_matching_result','ai_hr_policy_version','ai_hr_batch','ai_hr_batch_item') ORDER BY table_name;
