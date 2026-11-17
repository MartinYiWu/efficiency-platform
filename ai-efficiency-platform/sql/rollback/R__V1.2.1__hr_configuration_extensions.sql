-- 仅负责人确认无业务写入或已备份后受控执行；删除本版本新增表。
DROP TABLE ai_hr_configuration_audit;
DROP TABLE ai_hr_configuration_version;
DROP TABLE ai_hr_configuration_document;
