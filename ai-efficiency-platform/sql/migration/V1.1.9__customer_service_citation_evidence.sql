-- 未执行；须在部署任务6 Java代码前核验目标环境和迁移历史，授权后执行。
-- 模块 aiep-biz-aihub；影响 ai_customer_service_citation。
-- 回滚：sql/rollback/R__V1.1.9__customer_service_citation_evidence.sql；新事实存在时拒绝丢列。
-- 旧行保持 NULL；历史全文引用不回填推测的父ID或偏移。
ALTER TABLE ai_customer_service_citation
    ADD COLUMN parent_id VARCHAR(64) NULL COMMENT '冻结父片段ID，旧引用未记录',
    ADD COLUMN citation_type VARCHAR(32) NULL COMMENT 'FULL_PARENT或EXTRACTED_SPANS；NULL为旧引用',
    ADD COLUMN original_spans_json JSON NULL COMMENT '冻结原文偏移和哈希数组';
