SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ai_hr_interview_generation' ORDER BY ordinal_position;
