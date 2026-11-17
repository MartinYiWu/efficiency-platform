-- 只读验证结构、状态不变量；不读取加密正文、AAD内容或身份值。
SELECT COUNT(*) AS memory_table_count FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai\_memory\_%';
SELECT COUNT(*) AS memory_trigger_count FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg\_memory\_%';
SELECT COUNT(*) AS prefix_index_count FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name LIKE 'ai\_memory\_%' AND sub_part IS NOT NULL;
SELECT COUNT(*) AS invalid_current_count FROM ai_memory_item i LEFT JOIN ai_memory_version v ON v.tenant_id=i.tenant_id AND v.item_id=i.id AND v.id=i.current_version_id WHERE i.current_version_id IS NOT NULL AND (v.id IS NULL OR v.status<>'ACTIVE');
SELECT COUNT(*) AS duplicate_active_count FROM (SELECT tenant_id,item_id FROM ai_memory_version WHERE status='ACTIVE' GROUP BY tenant_id,item_id HAVING COUNT(*)>1) x;
SELECT COUNT(*) AS invalid_aad_count FROM ai_memory_version WHERE aad_tenant_id<>tenant_id OR aad_item_id<>item_id OR aad_version_id<>id OR aad_key_version<>key_version;
SELECT COUNT(*) AS invalid_deleted_body_count FROM ai_memory_version WHERE status='DELETED' AND (encrypted_payload IS NOT NULL OR nonce IS NOT NULL OR auth_tag IS NOT NULL OR content_hmac IS NOT NULL OR scrubbed_at IS NULL);
-- 预期：12表、12触发器，其余全0；语义并发/触发器行为仍须真实隔离集成测试。
