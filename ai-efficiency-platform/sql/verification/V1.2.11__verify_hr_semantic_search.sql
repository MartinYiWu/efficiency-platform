SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('ai_hr_semantic_search_job','ai_hr_semantic_search_source') ORDER BY ordinal_position;

