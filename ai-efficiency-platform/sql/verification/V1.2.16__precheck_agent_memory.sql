-- 只读预检；不输出账户/连接串/正文，不自动修复或写入。
-- 共享库需先核实实际迁移历史，再对精确DDL/hash及影响获得本模块授权。
SELECT VERSION() AS mysql_version, @@innodb_page_size AS innodb_page_size;
SELECT @@GLOBAL.log_bin AS binary_logging, @@GLOBAL.log_bin_trust_function_creators AS trigger_creation_trust;
-- binary_logging=1且trigger_creation_trust=0时，创建触发器需具备SUPER的管理会话。
-- 当前应用账号已实际返回1419；权限条件未满足前停止，不先创建部分对象，不自动更改全局变量或给应用账号提权。
SELECT COUNT(*) AS existing_memory_tables FROM information_schema.tables
 WHERE table_schema=DATABASE() AND table_name LIKE 'ai\_memory\_%';
SELECT COUNT(*) AS existing_memory_triggers FROM information_schema.triggers
 WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg\_memory\_%';
SELECT COUNT(*) AS existing_versioned_objects FROM information_schema.tables
 WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_session_binding','ai_memory_policy','ai_memory_policy_version','ai_memory_item','ai_memory_version','ai_memory_source','ai_memory_dependency','ai_memory_decision','ai_memory_suppression','ai_memory_outbox','ai_memory_deletion_job','ai_memory_tombstone');
-- 以上对象必须全部不存在；目标需MySQL8.0.16+、InnoDB/16K页及DYNAMIC行格式。
