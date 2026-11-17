-- 只读预检。目标必须是审核通过的专属技术schema；四个existing均须为NULL。
SELECT current_schema() AS target_schema,
       to_regclass('agent_memory_thread_execution') AS existing_execution,
       to_regclass('agent_memory_thread_member') AS existing_member,
       to_regclass('agent_memory_thread_namespace') AS existing_namespace,
       to_regclass('agent_memory_thread_resume') AS existing_resume;
SELECT version() AS postgres_version;
