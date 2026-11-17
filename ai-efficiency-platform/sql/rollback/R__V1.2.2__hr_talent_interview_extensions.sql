-- 受控回滚；仅在数据已备份且本迁移业务停止后人工执行。
DROP TABLE ai_hr_talent_operation;
DROP TABLE ai_hr_interview_export;
DROP TABLE ai_hr_audit;
DROP TABLE ai_hr_deletion_job;
DROP TABLE ai_hr_contact_grant;
DROP TABLE ai_hr_interview_assignment;
DROP TABLE ai_hr_interview_set;
DROP TABLE ai_hr_candidate_source;
DROP TABLE ai_hr_candidate_merge;
