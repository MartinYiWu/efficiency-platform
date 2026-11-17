-- 破坏性回滚：确认没有正式业务资料或已按授权备份后，另经确认执行；绝不自动运行。
DROP TABLE ai_hr_batch_item;
DROP TABLE ai_hr_batch;
DROP TABLE ai_hr_policy_version;
DROP TABLE ai_hr_matching_result;
DROP TABLE ai_hr_matching_run;
DROP TABLE ai_hr_semantic_snapshot;
DROP TABLE ai_hr_fact_snapshot;
DROP TABLE ai_hr_candidate;
DROP TABLE ai_hr_config_version;
DROP TABLE ai_hr_position_draft;
DROP TABLE ai_hr_position;
DROP TABLE ai_hr_position_sequence;
