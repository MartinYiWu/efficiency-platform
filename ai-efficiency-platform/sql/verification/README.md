# SQL 核验脚本

> 状态：有效  
> 文件命名：`V<版本>__verify_<lower_snake_case说明>.sql`

本目录只允许只读 `SELECT`、`SHOW`、`EXPLAIN` 和元数据核验语句。脚本应输出可比对的行数、状态分布、约束或索引结果；禁止任何 DDL、DML、会话变量写入或锁表语句。

- [V1.1.7 智能客服证据策略核验](V1.1.7__verify_customer_service_evidence_policy.sql)：版本、列结构与新策略范围检查。
