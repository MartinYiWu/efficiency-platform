-- 只读schema与数量验收；不输出偏好明文。
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai_memory_sharing_%';
SELECT table_name,column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name LIKE 'ai_memory_sharing_%' ORDER BY table_name,ordinal_position;
SELECT trigger_name,event_manipulation,event_object_table FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_sharing_%';
SELECT COUNT(*) AS invalid_projection_sources FROM ai_memory_sharing_projection p LEFT JOIN ai_memory_source s ON s.tenant_id=p.tenant_id AND s.id=p.id WHERE s.id IS NULL OR s.source_type<>'MEMORY_SHARE_GRANT' OR (p.state='REVOKED' AND s.deletion_epoch=0);
SELECT COUNT(*) AS invalid_active_scope_grants FROM ai_memory_sharing_grant g JOIN ai_memory_sharing_scope s ON s.tenant_id=g.tenant_id AND s.id=g.scope_id WHERE g.status='ACTIVE' AND s.status<>'ACTIVE';
