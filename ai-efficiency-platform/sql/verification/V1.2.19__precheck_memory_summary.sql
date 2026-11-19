-- 只读；输出必须在SQL审阅时逐项核对，不包含数据正文/凭据。
SELECT DATABASE() AS selected_schema;
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_source','ai_memory_dependency','ai_memory_packet','ai_memory_packet_refresh','ai_memory_session_binding');
SELECT COUNT(*) AS existing_summary_tables FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_summary_watermark','ai_memory_summary_source','ai_memory_summary_plan','ai_memory_summary_segment');
SELECT COUNT(*) AS existing_summary_triggers FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_summary_%';
SELECT table_name,column_name,column_type,is_nullable,column_default,collation_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_source','ai_memory_dependency','ai_memory_packet','ai_memory_packet_refresh') ORDER BY table_name,ordinal_position;
