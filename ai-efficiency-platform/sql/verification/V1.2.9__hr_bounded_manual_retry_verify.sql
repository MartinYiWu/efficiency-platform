SELECT table_name,column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ai_hr_item_retry' ORDER BY ordinal_position;
