SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ai_hr_audit_archive' ORDER BY ordinal_position;
SELECT table_name,index_name,column_name,seq_in_index FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='ai_hr_audit_archive' ORDER BY index_name,seq_in_index;
