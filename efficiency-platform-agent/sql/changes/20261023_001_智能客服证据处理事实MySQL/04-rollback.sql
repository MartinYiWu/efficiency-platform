-- 先回退应用并备份事实；此操作会丢失本列已保存数据，必须单独授权。
ALTER TABLE agent_customer_service_retrieval_snapshot DROP COLUMN retrieval_facts_json;
