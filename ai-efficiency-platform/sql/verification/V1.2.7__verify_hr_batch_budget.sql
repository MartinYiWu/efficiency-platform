SELECT column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ai_hr_batch_budget' ORDER BY ordinal_position;
SELECT index_name,non_unique,column_name FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='ai_hr_batch_budget' ORDER BY index_name,seq_in_index;
