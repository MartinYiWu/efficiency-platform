-- 只读Schema/数量验收；不读取候选或偏好正文。
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_proposal','ai_memory_proposal_batch','ai_memory_proposal_source_claim');
SELECT table_name,column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_proposal','ai_memory_proposal_batch','ai_memory_proposal_source_claim') ORDER BY table_name,ordinal_position;
SELECT trigger_name,event_manipulation,event_object_table FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_proposal_%' ORDER BY trigger_name;
SELECT constraint_name,constraint_type FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name IN ('ai_memory_proposal','ai_memory_proposal_batch','ai_memory_proposal_source_claim') ORDER BY table_name,constraint_name;
SELECT COUNT(*) AS invalid_proposals FROM ai_memory_proposal WHERE index_status<>'NOT_REQUESTED' OR JSON_LENGTH(dependencies_json)>512 OR JSON_LENGTH(source_message_ids_json)>128 OR (status='PENDING' AND encrypted_payload IS NULL);
SELECT COUNT(*) AS oversized_batches FROM (SELECT tenant_id,task_id,COUNT(*) AS n FROM ai_memory_proposal GROUP BY tenant_id,task_id HAVING COUNT(*)>16) invalid_batches;
SELECT COUNT(*) AS invalid_accepted FROM ai_memory_proposal p LEFT JOIN ai_memory_version v ON v.tenant_id=p.tenant_id AND v.item_id=p.item_id AND v.id=p.accepted_version_id WHERE p.status='ACCEPTED' AND (v.id IS NULL OR p.decision_action<>'CONFIRM');
