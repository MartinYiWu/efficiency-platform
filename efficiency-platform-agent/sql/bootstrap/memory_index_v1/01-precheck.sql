-- 当前连接必须已经选中经审阅的Agent专属schema；不自动创建/选择schema。
SELECT current_schema(), current_user;
DO $$ BEGIN
 IF current_schema() !~ '^(agent_runtime(_[a-f0-9]{8})?|s7_acceptance_[a-f0-9]{8})$' THEN
   RAISE EXCEPTION 'Agent owned schema required';
 END IF;
END $$;
SELECT table_name FROM information_schema.tables
 WHERE table_schema=current_schema() AND table_name LIKE 'memory_index_%';
