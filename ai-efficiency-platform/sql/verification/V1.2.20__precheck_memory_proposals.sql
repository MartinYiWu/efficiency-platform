-- 只读；核对目标schema、既有核心/packet/summary版本和对象缺席，不输出正文。
SELECT DATABASE() AS selected_schema;
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_item','ai_memory_version','ai_memory_decision','ai_memory_source','ai_memory_dependency','ai_memory_suppression','ai_memory_packet','ai_memory_packet_refresh');
SELECT COUNT(*) AS existing_proposal_tables FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_proposal','ai_memory_proposal_batch','ai_memory_proposal_source_claim');
SELECT trigger_name,event_object_table FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND (trigger_name LIKE 'trg_proposal_%' OR event_object_table IN ('ai_memory_source','ai_memory_suppression'));
