-- 仅限尚未执行任何普通变更的全新隔离库；否则必须停止并前滚修复。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM agent_runtime.schema_changes
        WHERE change_id <> 'agent_database_bootstrap_v1'
    ) THEN
        RAISE EXCEPTION 'agent_runtime 已承载普通变更，禁止删除 bootstrap schema';
    END IF;
END $$;
DROP SCHEMA IF EXISTS agent_runtime CASCADE;

