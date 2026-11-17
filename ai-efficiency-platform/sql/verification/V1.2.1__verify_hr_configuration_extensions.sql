-- 只读核对新增3张表、字段和索引；不读取配置正文。
SELECT table_name,column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('ai_hr_configuration_document','ai_hr_configuration_version','ai_hr_configuration_audit') ORDER BY table_name,ordinal_position;
SELECT table_name,index_name,non_unique,seq_in_index,column_name FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name IN ('ai_hr_configuration_document','ai_hr_configuration_version','ai_hr_configuration_audit') ORDER BY table_name,index_name,seq_in_index;
