-- 人工受控破坏性回滚；仅本次aiep_memory_it_日期_随机专属演练库可执行。
-- 已含真实业务记忆的库不得执行；正文scrub不可逆，先停写/备份并另行审阅迁移方案。
-- 不关闭FOREIGN_KEY_CHECKS，不删除其他业务对象；先解除两个显式循环FK。
DROP TRIGGER IF EXISTS trg_memory_suppression_delete;
DROP TRIGGER IF EXISTS trg_memory_suppression_update;
DROP TRIGGER IF EXISTS trg_memory_suppression_insert;
DROP TRIGGER IF EXISTS trg_memory_tombstone_delete;
DROP TRIGGER IF EXISTS trg_memory_tombstone_update;
DROP TRIGGER IF EXISTS trg_memory_source_update;
DROP TRIGGER IF EXISTS trg_memory_policy_version_delete;
DROP TRIGGER IF EXISTS trg_memory_policy_version_update;
DROP TRIGGER IF EXISTS trg_memory_version_delete;
DROP TRIGGER IF EXISTS trg_memory_version_update;
DROP TRIGGER IF EXISTS trg_memory_item_update;
DROP TRIGGER IF EXISTS trg_memory_item_insert;
ALTER TABLE ai_memory_item DROP FOREIGN KEY fk_memory_item_current;
ALTER TABLE ai_memory_policy DROP FOREIGN KEY fk_memory_policy_current;
DROP TABLE ai_memory_dependency;
DROP TABLE ai_memory_deletion_job;
DROP TABLE ai_memory_outbox;
DROP TABLE ai_memory_suppression;
DROP TABLE ai_memory_tombstone;
DROP TABLE ai_memory_version;
DROP TABLE ai_memory_decision;
DROP TABLE ai_memory_source;
DROP TABLE ai_memory_item;
DROP TABLE ai_memory_policy_version;
DROP TABLE ai_memory_policy;
DROP TABLE ai_memory_session_binding;
